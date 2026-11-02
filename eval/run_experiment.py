"""Sample apron frames, score GPT-4o and GPT-5.6 Luna, and record a Langfuse experiment."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from eval.azure_client import AzureVisionClient
from eval.cost import cost_usd, summarize_usage, token_counts
from eval.few_shot import EXAMPLES, few_shot_id, held_out_keys, prepare_examples, write_example_page
from eval.frames import extract_frames, frame_path, video_duration_s, write_contact_sheet
from eval.labels import STATES, Sample, build_samples
from eval.prompt import get_prompt, prompt_id
from eval.scoring import prediction_row, summarize

SMOKE_SIZE = 8
REQUEST_TIMEOUT_S = 180
MAX_CONCURRENCY = 4


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _timestamps_path(root: Path) -> Path:
    for candidate in (root / "timestamps.csv", root / "others" / "timestamps.csv"):
        if candidate.exists():
            return candidate
    raise FileNotFoundError("timestamps.csv not found at the project root or in others/")


def select_smoke(samples: list[Sample], size: int = SMOKE_SIZE) -> list[Sample]:
    """Cover every video, then as many distinct phases as the size allows."""
    chosen: list[Sample] = []
    seen_phases: set[str] = set()
    videos: list[str] = []
    for sample in samples:
        if sample.video not in videos:
            videos.append(sample.video)
    for video in videos:
        candidates = [sample for sample in samples if sample.video == video and not sample.near_boundary]
        if not candidates:
            candidates = [sample for sample in samples if sample.video == video]
        candidates.sort(key=lambda sample: (sample.phase in seen_phases, sample.timestamp_s))
        if candidates and len(chosen) < size:
            chosen.append(candidates[0])
            seen_phases.add(candidates[0].phase)
    for sample in samples:
        if len(chosen) >= size:
            break
        if sample.phase not in seen_phases:
            chosen.append(sample)
            seen_phases.add(sample.phase)
    for sample in samples:
        if len(chosen) >= size:
            break
        if sample not in chosen:
            chosen.append(sample)
    return chosen[:size]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate stand-state recognition on sampled frames.")
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--models", default="gpt-4o,gpt-5.6-luna")
    parser.add_argument("--prompt-version", choices=("basic", "detailed"), default="detailed")
    parser.add_argument("--few-shot", action="store_true", help="Send the held-out open-door and closed-door examples with each frame.")
    args = parser.parse_args(argv)
    if args.interval_seconds <= 0:
        parser.error("--interval-seconds must be positive")
    models = [model.strip() for model in args.models.split(",") if model.strip()]
    if not models:
        parser.error("--models must name at least one deployment")

    root = project_root()
    load_dotenv(root / ".env")
    output_dir = root / "outputs" / "vlm_eval"
    frames_dir = output_dir / "frames"
    videos_dir = root / "raw_videos"
    timestamps_path = _timestamps_path(root)

    prompt_text = get_prompt(args.prompt_version)
    active_prompt_id = prompt_id(prompt_text)
    examples = prepare_examples(videos_dir, output_dir) if args.few_shot else []
    active_few_shot_id = few_shot_id() if args.few_shot else None
    example_page = write_example_page(output_dir)
    print(
        f"prompt version={args.prompt_version} id={active_prompt_id} "
        f"few_shot={'on' if args.few_shot else 'off'}"
        + (f" examples={active_few_shot_id}" if active_few_shot_id else "")
    )
    print(f"Few-shot images: {example_page}")
    for path, _caption in examples:
        print(f"  sending {path}")

    durations = {path.stem: video_duration_s(path) for path in sorted(videos_dir.glob("*.mp4"))}
    samples = build_samples(timestamps_path, durations, args.interval_seconds)
    if args.few_shot:
        held_out = held_out_keys()
        samples = [sample for sample in samples if (sample.video, sample.timestamp_s) not in held_out]
    manifest_path = output_dir / f"manifest_{args.interval_seconds}s.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps([sample.to_dict() for sample in samples], indent=2),
        encoding="utf-8",
    )
    counts: dict[str, int] = {}
    for sample in samples:
        counts[sample.video] = counts.get(sample.video, 0) + 1
    print(f"{len(samples)} frames at every {args.interval_seconds}s: {counts}")

    extract_frames(samples, videos_dir, frames_dir)
    sheet_path = output_dir / "contact_sheet.html"
    write_contact_sheet(samples, frames_dir, sheet_path)
    print(f"Contact sheet: {sheet_path}")

    client = AzureVisionClient(
        root,
        output_dir / "cache",
        timeout_s=REQUEST_TIMEOUT_S,
        prompt_text=prompt_text,
        examples=examples,
        few_shot_id=active_few_shot_id,
    )
    smoke = select_smoke(samples)
    print("Smoke check on GPT-4o:")
    smoke_failed = False
    for sample in smoke:
        record = client.predict(
            model="gpt-4o",
            image_path=frame_path(frames_dir, sample),
            frame_id=sample.frame_id,
            interval_seconds=sample.interval_seconds,
            video=sample.video,
            timestamp_s=sample.timestamp_s,
        )
        status = "ok" if record["parse_ok"] else "PARSE FAILED"
        print(f"  {sample.frame_id} {sample.phase} truth={sample.truth()} {status}")
        if not record["parse_ok"]:
            smoke_failed = True
            print(f"    raw: {(record.get('raw_response') or record.get('error') or '')[:400]}")
    if smoke_failed:
        print("Stopping before the full run because the smoke frames did not return valid JSON.")
        return 1

    dataset_name = f"stand-state-frames-{args.interval_seconds}s-{args.prompt_version}"
    if args.few_shot:
        dataset_name += "-fewshot"
    experiment_urls = _run_langfuse(
        dataset_name=dataset_name,
        samples=samples,
        models=models,
        frames_dir=frames_dir,
        client=client,
        interval_seconds=args.interval_seconds,
        prompt_text=prompt_text,
        prompt_version=args.prompt_version,
        prompt_fingerprint=active_prompt_id,
        few_shot=args.few_shot,
        few_shot_fingerprint=active_few_shot_id,
    )
    report = {
        "interval_seconds": args.interval_seconds,
        "prompt_version": args.prompt_version,
        "prompt_id": active_prompt_id,
        "few_shot": args.few_shot,
        "few_shot_id": active_few_shot_id,
        "few_shot_examples": [example.example_id for example in EXAMPLES] if args.few_shot else [],
        "dataset": dataset_name,
        "experiments": experiment_urls,
        "models": {},
    }
    for model in models:
        rows = []
        records = []
        for sample in samples:
            record = client.predict(
                model=model,
                image_path=frame_path(frames_dir, sample),
                frame_id=sample.frame_id,
                interval_seconds=sample.interval_seconds,
                video=sample.video,
                timestamp_s=sample.timestamp_s,
            )
            records.append(record)
            rows.append(prediction_row(sample, record))
        summary = summarize(rows, interval_seconds=args.interval_seconds, model=model)
        summary.update(summarize_usage(model, records))
        summary["api_calls_this_process"] = client.api_calls.get(model, 0)
        summary["cache_hits_this_process"] = client.cache_hits.get(model, 0)
        summary["azure_spend_this_process_usd"] = client.spend_usd.get(model, 0.0)
        report["models"][model] = summary
    report_path = output_dir / "report.json"
    archive_path = output_dir / "report_previous.json"
    if report_path.exists() and not archive_path.exists():
        archive_path.write_bytes(report_path.read_bytes())
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report_tag = f"report_{args.prompt_version}_{active_prompt_id}"
    if args.few_shot:
        report_tag += f"_fewshot_{active_few_shot_id}"
    (output_dir / f"{report_tag}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report: {report_path}")
    _print_summary(report)
    return 0


def _run_langfuse(
    *,
    dataset_name: str,
    samples: list[Sample],
    models: list[str],
    frames_dir: Path,
    client: AzureVisionClient,
    interval_seconds: int,
    prompt_text: str,
    prompt_version: str,
    prompt_fingerprint: str,
    few_shot: bool,
    few_shot_fingerprint: str | None,
) -> dict[str, str]:
    from langfuse import Evaluation, get_client

    _prepare_langfuse_env()
    langfuse = get_client()
    try:
        langfuse.get_dataset(dataset_name)
    except Exception:
        langfuse.create_dataset(
            name=dataset_name,
            description="Apron frames labeled from timestamps.csv for parked, tunnel attached, and cargo doors open.",
            metadata={
                "interval_seconds": interval_seconds,
                "prompt_version": prompt_version,
                "prompt_id": prompt_fingerprint,
                "few_shot": few_shot,
                "few_shot_id": few_shot_fingerprint or "",
            },
        )
    capture_images = os.getenv("LANGFUSE_CAPTURE_IMAGES", "").strip().lower() in {"1", "true", "yes", "on"}
    for index, sample in enumerate(samples, start=1):
        langfuse.create_dataset_item(
            dataset_name=dataset_name,
            id=f"{dataset_name}-{sample.frame_id}",
            input={
                "frame_id": sample.frame_id,
                "video": sample.video,
                "timestamp_s": sample.timestamp_s,
                "prompt_version": prompt_version,
                "prompt_id": prompt_fingerprint,
                "few_shot": few_shot,
                "few_shot_id": few_shot_fingerprint or "",
                "prompt": prompt_text,
                "image_path": frame_path(frames_dir, sample).relative_to(project_root()).as_posix(),
            },
            expected_output=sample.truth(),
            metadata={
                "video": sample.video,
                "condition": sample.video.split("_")[0],
                "phase": sample.phase,
                "interval_seconds": interval_seconds,
                "timestamp_s": sample.timestamp_s,
                "seconds_to_boundary": sample.seconds_to_boundary,
                "near_boundary": sample.near_boundary,
                "prompt_version": prompt_version,
                "prompt_id": prompt_fingerprint,
                "few_shot": few_shot,
                "few_shot_id": few_shot_fingerprint or "",
            },
        )
        if index % 50 == 0 or index == len(samples):
            print(f"Dataset items {index}/{len(samples)}")
    dataset = langfuse.get_dataset(dataset_name, fetch_items_page_size=100)
    urls: dict[str, str] = {}

    def task(*, item, **kwargs):
        image_path = project_root() / item.input["image_path"]
        model = kwargs["model"]
        record = client.predict(
            model=model,
            image_path=image_path,
            frame_id=item.input["frame_id"],
            interval_seconds=interval_seconds,
            video=item.input["video"],
            timestamp_s=item.input["timestamp_s"],
        )
        _trace_call(
            langfuse,
            model=model,
            image_path=image_path,
            examples=client.examples,
            record=record,
            capture_images=capture_images,
        )
        if record["parse_ok"]:
            return record["parsed"]
        return {
            "parked": None,
            "tunnel_attached": None,
            "doors_open": None,
            "description": None,
            "parse_ok": False,
            "error": record.get("error"),
        }

    def evaluator_for(state: str):
        def evaluator(*, output, expected_output, **kwargs):
            predicted = output.get(state) if isinstance(output, dict) else None
            actual = expected_output.get(state) if isinstance(expected_output, dict) else None
            correct = isinstance(predicted, bool) and predicted == actual
            return Evaluation(name=f"{state}_correct", value=1.0 if correct else 0.0)
        return evaluator

    def exact_match(*, output, expected_output, **kwargs):
        if not isinstance(output, dict) or not isinstance(expected_output, dict):
            return Evaluation(name="exact_match", value=0.0)
        correct = all(isinstance(output.get(state), bool) and output.get(state) == expected_output.get(state) for state in STATES)
        return Evaluation(name="exact_match", value=1.0 if correct else 0.0)

    evaluators = [evaluator_for(state) for state in STATES] + [exact_match]
    for model in models:
        print(f"Experiment {model}")

        async def model_task(*, item, _model=model, **kwargs):
            return await asyncio.to_thread(task, item=item, model=_model)

        result = dataset.run_experiment(
            name="Stand state recognition",
            run_name=_run_name(model, interval_seconds, prompt_version, prompt_fingerprint, few_shot, few_shot_fingerprint),
            description=(
                f"{model} on one frame every {interval_seconds} seconds. "
                f"Prompt version {prompt_version} ({prompt_fingerprint}). "
                f"Few-shot {'on' if few_shot else 'off'}."
            ),
            task=model_task,
            evaluators=evaluators,
            max_concurrency=MAX_CONCURRENCY,
            metadata={
                "model": model,
                "interval_seconds": str(interval_seconds),
                "prompt_version": prompt_version,
                "prompt_id": prompt_fingerprint,
                "few_shot": "true" if few_shot else "false",
                "few_shot_id": few_shot_fingerprint or "",
            },
        )
        url = getattr(result, "experiment_url", None) or getattr(result, "dataset_run_url", "")
        urls[model] = url or ""
        print(result.format())
        if url:
            print(url)
    langfuse.flush()
    return urls


def _trace_call(langfuse, *, model: str, image_path: Path, examples: list[tuple[Path, str]], record: dict, capture_images: bool) -> None:
    """Record the images that were sent and the token cost on the dataset-run trace."""
    from langfuse.media import LangfuseMedia
    counts = token_counts(record.get("usage"))
    priced = cost_usd(model, record.get("usage")) if record.get("usage") else None
    generation_input: dict = {
        "frame_id": image_path.stem,
        "images_sent": 1 + len(examples),
        "example_images": [path.name for path, _caption in examples],
        "cache_hit": bool(record.get("cache_hit")),
    }
    if capture_images:
        generation_input["image"] = LangfuseMedia(file_path=str(image_path), content_type="image/jpeg")
        generation_input["examples"] = [
            {"caption": caption, "image": LangfuseMedia(file_path=str(path), content_type="image/jpeg")}
            for path, caption in examples
        ]
    update = {
        "output": record.get("parsed") or {"error": record.get("error"), "raw_response": record.get("raw_response")},
        "usage_details": {
            "input": counts["input_tokens"],
            "output": counts["output_tokens"],
            "total": counts["input_tokens"] + counts["output_tokens"],
            "cache_read_input_tokens": counts["cached_input_tokens"],
        },
        "metadata": {
            "cache_hit": bool(record.get("cache_hit")),
            "images_sent": 1 + len(examples),
            "example_images": [path.name for path, _caption in examples],
        },
    }
    if priced is not None:
        update["cost_details"] = {
            "input": priced["input"],
            "cache_read": priced["cached_input"],
            "output": priced["output"],
            "total": priced["total"],
        }
    try:
        with langfuse.start_as_current_observation(
            name="azure-vision",
            as_type="generation",
            model=model,
            input=generation_input,
        ) as generation:
            generation.update(**update)
    except Exception as exc:
        print(f"Could not record usage for {image_path.name}: {exc}")


def _run_name(model: str, interval_seconds: int, prompt_version: str, prompt_fingerprint: str, few_shot: bool, few_shot_fingerprint: str | None) -> str:
    name = f"{model}-every-{interval_seconds}s-{prompt_version}-{prompt_fingerprint}"
    if few_shot:
        name += f"-fewshot-{few_shot_fingerprint}"
    return name


def _prepare_langfuse_env() -> None:
    if not os.getenv("LANGFUSE_HOST") and os.getenv("LANGFUSE_BASE_URL"):
        os.environ["LANGFUSE_HOST"] = os.environ["LANGFUSE_BASE_URL"]


def _print_summary(report: dict) -> None:
    for model, summary in report["models"].items():
        overall = summary["overall"]
        print(
            f"\n{model}  version={report['prompt_version']}  few_shot={report['few_shot']}  "
            f"exact_match={overall['exact_match']}  parse_failures={overall['parse_failures']}"
        )
        for state, metrics in overall["states"].items():
            print(
                f"  {state}: acc={metrics['accuracy']} prec={metrics['precision']} "
                f"rec={metrics['recall']} f1={metrics['f1']} "
                f"positive={metrics['positive']} negative={metrics['negative']}"
            )
        flicker_summary = summary["flicker"]
        cost = summary.get("cost_usd") or {}
        print(
            f"  flicker: {flicker_summary['prediction_flips']} flips "
            f"in {flicker_summary['stable_pairs']} stable pairs"
        )
        print(
            f"  cost: ${cost.get('total')}  "
            f"input_tokens={summary['usage']['input_tokens']} "
            f"cached={summary['usage']['cached_input_tokens']} "
            f"output_tokens={summary['usage']['output_tokens']}  "
            f"api_calls_this_process={summary['api_calls_this_process']} "
            f"spend_this_process=${summary['azure_spend_this_process_usd']}"
        )


if __name__ == "__main__":
    sys.exit(main())

"""Sample apron frames, score the selected models, and record a Langfuse experiment."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from eval.azure_client import KNOWN_MODELS, AzureVisionClient, is_openrouter, openrouter_key
from eval.cost import cost_usd, summarize_usage, token_counts
from eval.few_shot import EXAMPLE_SETS, example_set_for_level, few_shot_id, held_out_keys, prepare_examples
from eval.frames import extract_frames, frame_path, video_duration_s, write_contact_sheet
from eval.labels import STATES, Sample, build_samples
from eval.prompt import PROMPT_LEVELS, prompt_id, prompt_text_for_level, selected_prompt_levels
from eval.scoring import prediction_row, summarize

SMOKE_SIZE = 8
SMOKE_MODEL = "gpt-5.6-luna"
REQUEST_TIMEOUT_S = 180
MAX_CONCURRENCY = 4

# Each level includes the one before it. Azure models first, then the OpenRouter models.
DEFAULT_MODELS = ["gpt-5.6-luna", "gpt-6-luna", "gpt-4o"]
MID_MODELS = [*DEFAULT_MODELS, "gpt-6.1-terra", "gpt-6.2-sol"]
HIGH_MODELS = [*MID_MODELS, "gpt-6-astra", "google/gemma-4-31b-it", "qwen/qwen3.8-flash"]


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
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for generated frames, caches, manifests, and reports (default: outputs/vlm_eval).",
    )
    parser.add_argument(
        "--langfuse",
        action="store_true",
        help="Create Langfuse dataset items and experiments (disabled by default).",
    )
    parser.add_argument(
        "--models",
        help="Comma-separated model ids. Replaces the level's list; cannot be combined with --mid or --high.",
    )
    levels = parser.add_mutually_exclusive_group()
    levels.add_argument(
        "--mid",
        action="store_true",
        help="Default models plus gpt-6.1-terra and gpt-6.2-sol.",
    )
    levels.add_argument(
        "--high",
        action="store_true",
        help="Every registered model: --mid plus gpt-6-astra, Gemma 4 31B (paid), and Qwen3.8 Flash.",
    )
    parser.add_argument(
        "--prompt-level",
        type=int,
        choices=PROMPT_LEVELS,
        default=None,
        help=(
            "1: simple prompt. 2: descriptive prompt. 3: descriptive prompt with 2 examples. "
            "4: descriptive prompt with 10 examples. Default: run all levels (1–4)."
        ),
    )
    args = parser.parse_args(argv)
    if args.interval_seconds <= 0:
        parser.error("--interval-seconds must be positive")
    if args.models is not None:
        if args.mid or args.high:
            parser.error("--models cannot be combined with --mid or --high")
        models = [model.strip() for model in args.models.split(",") if model.strip()]
        if not models:
            parser.error("--models must name at least one deployment")
    else:
        models = HIGH_MODELS if args.high else MID_MODELS if args.mid else DEFAULT_MODELS
    unknown = [model for model in models if model not in KNOWN_MODELS]
    if unknown:
        parser.error(f"Unknown model(s): {', '.join(unknown)}")

    root = project_root()
    load_dotenv(root / ".env")
    if any(is_openrouter(model) for model in models) and not openrouter_key():
        parser.error("OPENROUTER_API_KEY (or OPEN_ROUTER_API_KEY) is required for the OpenRouter models")
    print(f"models: {', '.join(models)}")
    output_dir = args.output_dir or root / "outputs" / "vlm_eval"
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    frames_dir = output_dir / "frames"
    videos_dir = root / "raw_videos"
    timestamps_path = _timestamps_path(root)

    model_level = "custom" if args.models is not None else "high" if args.high else "mid" if args.mid else "default"
    for prompt_level in selected_prompt_levels(args.prompt_level):
        result = _run_prompt_level(
            root=root,
            output_dir=output_dir,
            frames_dir=frames_dir,
            videos_dir=videos_dir,
            timestamps_path=timestamps_path,
            models=models,
            model_level=model_level,
            interval_seconds=args.interval_seconds,
            prompt_level=prompt_level,
            langfuse_enabled=args.langfuse,
        )
        if result:
            return result
    return 0


def _run_prompt_level(
    *,
    root: Path,
    output_dir: Path,
    frames_dir: Path,
    videos_dir: Path,
    timestamps_path: Path,
    models: list[str],
    model_level: str,
    interval_seconds: int,
    prompt_level: int,
    langfuse_enabled: bool,
) -> int:
    prompt_text = prompt_text_for_level(prompt_level)
    active_prompt_id = prompt_id(prompt_text)
    set_name = example_set_for_level(prompt_level)
    example_set = EXAMPLE_SETS[set_name] if set_name else ()
    examples = prepare_examples(videos_dir, output_dir, set_name) if set_name else []
    active_few_shot_id = few_shot_id(example_set) if set_name else None
    print(
        f"prompt level={prompt_level} id={active_prompt_id} "
        f"examples={set_name or 'none'}"
        + (f" ({active_few_shot_id})" if active_few_shot_id else "")
    )
    if set_name:
        print(f"Example images: {output_dir / 'few_shot' / (set_name + '.html')}")
    for path, _caption in examples:
        print(f"  sending {path}")

    durations = {path.stem: video_duration_s(path) for path in sorted(videos_dir.glob("*.mp4"))}
    samples = build_samples(timestamps_path, durations, interval_seconds)
    if example_set:
        held_out = held_out_keys(example_set)
        samples = [sample for sample in samples if (sample.video, sample.timestamp_s) not in held_out]
    manifest_path = output_dir / f"manifest_{interval_seconds}s.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps([sample.to_dict() for sample in samples], indent=2),
        encoding="utf-8",
    )
    counts: dict[str, int] = {}
    for sample in samples:
        counts[sample.video] = counts.get(sample.video, 0) + 1
    print(f"{len(samples)} frames at every {interval_seconds}s: {counts}")

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
    print(f"Smoke check on {SMOKE_MODEL}:")
    smoke_failed = False
    for index, sample in enumerate(smoke, start=1):
        print(f"Smoke {SMOKE_MODEL} {index}/{len(smoke)} {sample.frame_id} ...", end="", flush=True)
        record = client.predict(
            model=SMOKE_MODEL,
            image_path=frame_path(frames_dir, sample),
            frame_id=sample.frame_id,
            interval_seconds=sample.interval_seconds,
            video=sample.video,
            timestamp_s=sample.timestamp_s,
        )
        print(f" {'cache hit' if record.get('cache_hit') else 'done'}", flush=True)
        status = "ok" if record["parse_ok"] else "PARSE FAILED"
        print(f"  {sample.frame_id} {sample.phase} truth={sample.truth()} {status}")
        if not record["parse_ok"]:
            smoke_failed = True
            print(f"    raw: {(record.get('raw_response') or record.get('error') or '')[:400]}")
    if smoke_failed:
        print("Stopping before the full run because the smoke frames did not return valid JSON.")
        return 1

    dataset_name = f"stand-state-frames-{interval_seconds}s-level{prompt_level}"
    experiment_urls: dict[str, str] = {}
    if langfuse_enabled:
        experiment_urls = _run_langfuse(
            dataset_name=dataset_name,
            samples=samples,
            models=models,
            frames_dir=frames_dir,
            client=client,
            interval_seconds=interval_seconds,
            prompt_text=prompt_text,
            prompt_level=prompt_level,
            prompt_fingerprint=active_prompt_id,
            example_set=set_name,
            few_shot_fingerprint=active_few_shot_id,
        )
    report = {
        "interval_seconds": interval_seconds,
        "prompt_level": prompt_level,
        "model_level": model_level,
        "prompt_id": active_prompt_id,
        "example_set": set_name,
        "few_shot_id": active_few_shot_id,
        "few_shot_examples": [example.example_id for example in example_set],
        "dataset": dataset_name if langfuse_enabled else None,
        "experiments": experiment_urls,
        "models": {},
    }
    for model in models:
        rows = []
        records = []
        for index, sample in enumerate(samples, start=1):
            print(f"{model} {index}/{len(samples)} {sample.frame_id} ...", end="", flush=True)
            record = client.predict(
                model=model,
                image_path=frame_path(frames_dir, sample),
                frame_id=sample.frame_id,
                interval_seconds=sample.interval_seconds,
                video=sample.video,
                timestamp_s=sample.timestamp_s,
            )
            print(f" {'cache hit' if record.get('cache_hit') else 'done'}", flush=True)
            records.append(record)
            rows.append(prediction_row(sample, record))
        summary = summarize(rows, interval_seconds=interval_seconds, model=model)
        summary.update(summarize_usage(model, records))
        summary["api_calls_this_process"] = client.api_calls.get(model, 0)
        summary["cache_hits_this_process"] = client.cache_hits.get(model, 0)
        summary["azure_spend_this_process_usd"] = client.spend_usd.get(model, 0.0)
        report["models"][model] = summary
    report_path = output_dir / f"report_level{prompt_level}_{model_level}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
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
    prompt_level: int,
    prompt_fingerprint: str,
    example_set: str | None,
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
                "prompt_level": prompt_level,
                "prompt_id": prompt_fingerprint,
                "example_set": example_set or "none",
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
                "prompt_level": prompt_level,
                "prompt_id": prompt_fingerprint,
                "example_set": example_set or "none",
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
                "prompt_level": prompt_level,
                "prompt_id": prompt_fingerprint,
                "example_set": example_set or "none",
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
            run_name=_run_name(model, interval_seconds, prompt_level, prompt_fingerprint, example_set, few_shot_fingerprint),
            description=(
                f"{model} on one frame every {interval_seconds} seconds. "
                f"Prompt level {prompt_level} ({prompt_fingerprint}). "
                f"Examples: {example_set or 'none'}."
            ),
            task=model_task,
            evaluators=evaluators,
            max_concurrency=MAX_CONCURRENCY,
            metadata={
                "model": model,
                "interval_seconds": str(interval_seconds),
                "prompt_level": prompt_level,
                "prompt_id": prompt_fingerprint,
                "example_set": example_set or "none",
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


def _run_name(
    model: str,
    interval_seconds: int,
    prompt_level: int,
    prompt_fingerprint: str,
    example_set: str | None,
    few_shot_fingerprint: str | None,
) -> str:
    name = f"{model}-every-{interval_seconds}s-level{prompt_level}-{prompt_fingerprint}"
    if example_set:
        name += f"-{example_set}-{few_shot_fingerprint}"
    return name


def _prepare_langfuse_env() -> None:
    if not os.getenv("LANGFUSE_HOST") and os.getenv("LANGFUSE_BASE_URL"):
        os.environ["LANGFUSE_HOST"] = os.environ["LANGFUSE_BASE_URL"]


def _print_summary(report: dict) -> None:
    for model, summary in report["models"].items():
        overall = summary["overall"]
        print(
            f"\n{model}  level={report['prompt_level']}  examples={report['example_set'] or 'none'}  "
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

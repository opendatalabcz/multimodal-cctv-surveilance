# Stand-state evaluation

This evaluation scores vision models on single frames from a fixed airport apron camera. Each frame is judged for three states:

- `parked` — the aircraft nose wheel is stopped on the yellow parking cross
- `tunnel_attached` — the passenger jet bridge is fully docked
- `doors_open` — a cargo hold is open (passenger doors do not count)

Ground truth is `timestamps.csv`. `eval/run_experiment.py` samples the videos in `raw_videos/`, calls Azure OpenAI (and OpenRouter for the Gemma and Qwen models), and writes accuracy, flicker, and cost under `outputs/vlm_eval/`. Langfuse dataset experiments and traces are disabled by default; pass `--langfuse` to enable them.

## Data

Four clips, named by weather: `cloudy_6`, `night_6`, `rainy_6`, `sunny_6`.

`timestamps.csv` has one row per video. A state is true from its start time up to, but not including, its end time. The value `end` means the state lasts until the video ends.

| State | Start column | End column |
| --- | --- | --- |
| `parked` | `parked` | `left_parking` |
| `tunnel_attached` | `tunnel_attached` | `tunnel_detached` |
| `doors_open` | `doors_open` | `doors_closed` |

The default grid is one frame every 60 seconds, starting at 0, while the timestamp is at least one second inside the file. A frame within 20 seconds of a state change is marked `near_boundary`.

## Prompt levels and examples

The model must return one JSON object with `parked`, `tunnel_attached`, `doors_open`, and `description`. By default, `eval/run_experiment.py` runs all four levels in order; `--prompt-level` selects only the specified level. The prompt text is in `eval/prompt.py`, and the example frames are in `eval/few_shot.py`.
Use `--output-dir` to write a run's frames, cache, manifest, and reports to a separate directory instead of the default `outputs/vlm_eval`.

| Level | Prompt | Examples sent with each frame |
| --- | --- | --- |
| 1 | Simple: the three states and the output format, no visual hints | none |
| 2 | Descriptive: adds what to focus on and what to avoid for each state | none |
| 3 | Descriptive | `4-shot`: all-false, parked, parked+tunnel, and all-true frames from `cloudy1.mp4` |
| 4 | Descriptive | `6-shot`: the four level-3 examples plus all-true and parked-with-tunnel-and-cargo-doors closed frames from `cloudy1.mp4` |

The example frames are held out from `cloudy1.mp4` and are never scored. The JPEGs and the JSON sent with them are written to `outputs/vlm_eval/few_shot/4-shot.html` and `outputs/vlm_eval/few_shot/6-shot.html`.

When all prompt levels are selected, the levels run sequentially. Within each level, model runs execute in parallel while each model processes its frames sequentially (one in-flight request per model), including with `--langfuse`.

If the first reply is not that JSON object, the frame is sent once more with a repair prompt. A reply that still does not parse counts as wrong.

## Models

| Deployment | API | Level | Input / cached / output, USD per 1M tokens |
| --- | --- | --- | --- |
| `gpt-5.6-luna` | Responses API, reasoning effort `medium` | default | 0.20 / 0.02 / 1.20 |
| `gpt-6-luna` | Responses API, reasoning effort `medium` | default | 0.10 / 0.01 / 0.50 |
| `gpt-4o` | Chat Completions | default | 2.50 / 1.25 / 10.00 |
| `gpt-6.1-terra` | Responses API, reasoning effort `medium` | `--mid` | 1.00 / 0.05 / 5.00 |
| `gpt-6.2-sol` | Responses API, reasoning effort `medium` | `--mid` | 2.00 / 0.10 / 10.00 |
| `gpt-6-astra` | Responses API, reasoning effort `medium` | `--high` | 10.00 / 1.00 / 50.00 |
| `google/gemma-4-31b-it` | OpenRouter chat completions (paid) | `--high` | token counts only |
| `qwen/qwen3.8-flash` | OpenRouter chat completions | `--high` | token counts only |

Prices are Azure OpenAI Global Standard, short context. Confirm the `gpt-6.2-sol` price in the Azure portal before trusting the cost column. The OpenRouter models have no price in `eval/cost.py`, so only their token counts are recorded.

Levels include the ones before them:

- **Default** (`python -m eval.run_experiment`): `gpt-5.6-luna`, `gpt-6-luna`, `gpt-4o`
- **`--mid`**: default plus `gpt-6.1-terra` and `gpt-6.2-sol`
- **`--high`**: every model above, including `gpt-6-astra`, Gemma 4 31B, and Qwen3.8 Flash

`--models` takes an exact comma-separated list instead of a level. Passing `--models` with `--mid` or `--high`, or passing two level flags, is an error.

Before each run, eight frames are sent to `gpt-5.6-luna`. The full run starts only if every smoke frame returns valid JSON.

The OpenRouter models need `OPENROUTER_API_KEY` in `.env`. `OPEN_ROUTER_API_KEY` is also accepted. The run stops before any frame is sent if a selected model needs the key and it is missing.

Each answer is cached under `outputs/vlm_eval/cache/` by model, interval, prompt id, and few-shot id. A transport failure is not cached, so a later run can retry it. Token cost uses the Azure prices in `eval/cost.py`.

## Metrics

For each state: accuracy, precision, recall, and F1. `exact_match` is the share of frames where all three booleans are correct. Parse failures count as incorrect and are reported separately.

Flicker is a prediction change between two adjacent frames on the same video whose ground truth did not change.

Figures are written overall, per video, and for the near-boundary frames.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r eval/requirements.txt
```

Put these in `.env` at the project root. The endpoint may be the Azure resource root or a URL that already ends in `/openai/v1`.

- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `OPENROUTER_API_KEY` — only for `--high` or `--models` that include Gemma or Qwen
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL` (or `LANGFUSE_HOST`) — only when using `--langfuse`
- `LANGFUSE_CAPTURE_IMAGES` — set to `true` to attach the JPEGs to Langfuse traces

## Run

```bash
python -m eval.test_labels
python -m eval.test_visualizations
python -m eval.run_experiment                                  # levels 1–4, default models; no Langfuse
python -m eval.run_experiment --langfuse                       # enable Langfuse dataset experiments and traces
python -m eval.run_experiment --prompt-level 1
python -m eval.run_experiment --prompt-level 3 --mid
python -m eval.run_experiment --prompt-level 4 --high --interval-seconds 60
python -m eval.run_experiment --prompt-level 4 --models gpt-4o,gpt-5.6-luna
```

## Visualize results

After generating experiment reports, create static accuracy plots without sending model requests or Langfuse traces:

```bash
uv pip install --python .venv/bin/python -r eval/requirements.txt
uv run --python .venv/bin/python python -m eval.visualize_results
uv run --python .venv/bin/python python -m eval.visualize_results --model gpt-4o --prompt-level 3
```

The default command plots exact-match and per-state accuracy across prompt levels for each interval/model tier found in the reports. Add `--model` and `--prompt-level` together to also generate four confusion matrices (combined across all three state decisions, then one per state). The combined and per-state matrices use Yes/No axes and count annotations; parse failures are excluded and noted. Use `--model-level` and/or `--interval-seconds` to filter reports or resolve an ambiguous model selection. PNGs are written to `outputs/vlm_eval/plots/` by default; `--output-dir` changes the destination.

## Outputs

All of these are under `outputs/vlm_eval/`:

- `frames/{interval}s/` — one JPEG per scored timestamp
- `manifest_{interval}s.json` — the scored samples and their labels
- `contact_sheet.html` — every frame with its label; near-boundary frames are highlighted
- `few_shot/` — example JPEGs, plus `4-shot.html` and `6-shot.html` for levels 3 and 4
- `cache/` — raw model replies
- `report_level{n}_{model_level}.json` — one summary per prompt level and model level. `model_level` is `default`, `mid`, `high`, or `custom` for `--models`. Runs at different levels no longer overwrite each other. Earlier `report.json` and `report_previous.json` files are not written any more.
- `plots/` — accuracy-comparison PNGs and, when selected with `--model` and `--prompt-level`, confusion-matrix PNGs.

`raw_videos/` and `outputs/` are gitignored. `camera_images/` is earlier collected stills and is not read by this evaluation.

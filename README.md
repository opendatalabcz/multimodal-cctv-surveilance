# Stand-state evaluation

This evaluation scores vision models on single frames from a fixed airport apron camera. Each frame is judged for three states:

- `parked` — the aircraft nose wheel is stopped on the yellow parking cross
- `tunnel_attached` — the passenger jet bridge is fully docked
- `doors_open` — a cargo hold is open (passenger doors do not count)

Ground truth is `timestamps.csv`. `eval/run_experiment.py` samples the videos in `raw_videos/`, calls Azure OpenAI (and OpenRouter for the Gemma and Qwen models), and writes accuracy, flicker, and cost under `outputs/vlm_eval/`. The same items are recorded as a Langfuse dataset experiment.

## Data

Four clips, named by weather: `cloudy_6`, `night_6`, `rainy_6`, `sunny_6`.

`timestamps.csv` has one row per video. A state is true from its start time up to, but not including, its end time. The value `end` means the state lasts until the video ends.

| State | Start column | End column |
| --- | --- | --- |
| `parked` | `parked` | `left_parking` |
| `tunnel_attached` | `tunnel_attached` | `tunnel_detached` |
| `doors_open` | `doors_open` | `doors_closed` |

The default grid is one frame every 60 seconds, starting at 0, while the timestamp is at least one second inside the file. A frame within 20 seconds of a state change is marked `near_boundary`.

## Prompt and examples

The model must return one JSON object with `parked`, `tunnel_attached`, `doors_open`, and `description`. Two wordings live in `eval/prompt.py`:

- `basic` — cargo-door rule only
- `detailed` — also says either the front or rear hold counts, and that the rear hold can sit partly behind the wing

`--prompt-version` selects one. The default is `detailed`. If the first reply is not that JSON object, the frame is sent once more with a repair prompt. A reply that still does not parse counts as wrong.

`--few-shot` sends two held-out `night_6` frames ahead of the frame being judged: cargo hold open at 1530s, and both holds closed at 2430s while the aircraft is still parked and the bridge is still docked. Those times sit off the 60-second grid. If a chosen interval would score them, they are left out of the scored set. The JPEGs and the JSON sent with them are written to `outputs/vlm_eval/few_shot/index.html`.

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
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- `LANGFUSE_BASE_URL` (or `LANGFUSE_HOST`)
- `LANGFUSE_CAPTURE_IMAGES` — set to `true` to attach the JPEGs to the Langfuse trace

## Run

```bash
python -m eval.test_labels
python -m eval.run_experiment
python -m eval.run_experiment --few-shot
python -m eval.run_experiment --mid
python -m eval.run_experiment --high --interval-seconds 60 --prompt-version detailed
python -m eval.run_experiment --interval-seconds 60 --prompt-version detailed --models gpt-4o,gpt-5.6-luna
```

## Outputs

All of these are under `outputs/vlm_eval/`:

- `frames/{interval}s/` — one JPEG per scored timestamp
- `manifest_{interval}s.json` — the scored samples and their labels
- `contact_sheet.html` — every frame with its label; near-boundary frames are highlighted
- `few_shot/` — example JPEGs and `index.html` when `--few-shot` is on
- `cache/` — raw model replies
- `report.json` — the latest summary
- `report_{version}_{prompt_id}[_fewshot_{id}].json` — a copy that does not overwrite an earlier prompt or example set

`raw_videos/` and `outputs/` are gitignored. `camera_images/` is earlier collected stills and is not read by this evaluation.

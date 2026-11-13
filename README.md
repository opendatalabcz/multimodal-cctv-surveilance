# CCTV agent

A FastAPI chat API and a React UI for looking at configured CCTV stills. The model runs a custom Azure function-calling loop: it fetches frames, then finishes the turn by calling `submit_answer`. The UI talks to the API over `/api` only.

Runtime detail is in [docs/AGENT.md](docs/AGENT.md).

## Catalog

Cameras are grouped **sector → location → camera**. A camera is available only when the sector, the location, and the camera are all enabled.

The committed catalog has **27 cameras** in three sectors:

| Sector | Locations | Cameras |
| --- | --- | --- |
| Prague | 14 | 22 stills from the city camera portal |
| Japan | Tokachi-Obihiro, Tokyo Airport | 2 YouTube livestreams |
| Namibia | Desert, Small Pond, River | 3 YouTube livestreams |

Prague locations: Charles Bridge (2), Holešovičky (2), Budějovická (1), Nuselský most (2), Barrandovský most (2), Hybernská (1), Bělocerkevská (1), Ječná (1), Mariánské náměstí (1), Argentinská (3), Strahovský tunel (2), Tunel Mrázovka (2), Náměstí Kinských (1), Malostranská (1).

A Prague camera id is `{location_id}_{portal id}` and its name is that portal id, for example `charles_bridge_101200` / `101200`. A livestream id ends in `_live`, for example `tokachi_obihiro_live`.

## Config

| File | What it holds |
| --- | --- |
| `configs/cameras.yaml` | Sectors, locations, cameras, and scene analysis |
| `configs/agent.yaml` | Model catalog, selected model, reasoning, verbosity, and tool toggles |
| `configs/eval_questions.yaml` | Questions asked by `make eval` |

`GET/PUT /api/config` reads and writes those files. The Config panel saves camera edits to `cameras.yaml`, and model, reasoning, verbosity, and tool toggles to `agent.yaml`. Secrets stay in the environment.

## Chat

- The header selects the model. `configs/agent.yaml` selects GPT-4o. GPT-5.6 Luna and GPT-6 Astra are also listed. Luna and Astra can set reasoning effort and verbosity; GPT-4o cannot.
- `list_cameras` and `get_camera_image` are always available. Image results are paged using the selected model's `max_images_per_request` (32 for the shipped models), with `next_offset` when another page remains.
- Optional tools follow three independent toggles: `internet` (DuckDuckGo), `weather` (Open-Meteo), and `maps` (OpenStreetMap Nominatim). A fourth toggle, `annotations`, is off by default. Toggles apply on the next message.
- A turn ends only when the model calls `submit_answer` with the visible markdown, the frames to show, and up to three follow-up questions. With `annotations` on, the model adds a box, point, line, or polygon only when it is sure of the object and its place; the answer text does not draw on the picture. A follow-up can mark a frame already shown; that still is shown again with the new marks. With the toggle off, the model is told to leave annotations empty and the UI hides marks already stored on a turn. Turning it back on shows those stored marks. Valid highlights are not limited to eight; a 1,000-annotation platform guard protects the response.
- Conversations live in memory and reset when the API stops. Each turn also appends a line to `logs/chat_turns.jsonl`. Langfuse tracing is off unless `LANGFUSE_ENABLED` and both Langfuse keys are set.

External services are public demo APIs without an uptime guarantee.

## Run locally

```bash
make install_dev
make up
```

`make install_dev` installs the Python package (including pytest) and the frontend dependencies. `make up` starts the API on port 8000 and the UI on port 5173. The UI proxies `/api` to the API.

`make api` and `make ui` start one process. `make help` lists every target.

## Evaluation

```bash
make eval
```

`make eval` asks each question in `configs/eval_questions.yaml` once per catalog model and verbosity, each in a fresh chat, and writes `outputs/end_to_end_eval/`. A model with unlocked verbosity gets a folder per level (`low`, `medium`, `high`). GPT-4o has verbosity locked, so its question folders sit directly under the model. A folder that already contains `result.json` is skipped. The API does not need to be running. Azure credentials and reachable cameras do. The command does not change `configs/agent.yaml`.

```bash
uv run cctv-eval --model gpt-4o --question charles-bridge-walk
uv run cctv-eval --verbosity low --force
uv run cctv-eval --screenshot
```

`--screenshot` also saves `screenshot.png` from the UI. That needs `make up` and a one-time `uv run playwright install chromium`. The browser asks the question again, and the header's model and verbosity selects save `configs/agent.yaml` for that turn. The runner restores the file afterward. If the browser step fails, the answer files stay and the error is recorded in `result.json`.

### Grading

```bash
make eval-report
```

`make eval-report` makes no model calls. It rewrites `outputs/end_to_end_eval/grading.csv` from every `result.json`, with one row per answer. Token counts and `model_calls` cover the whole turn. `selection_precision` and `selection_recall` compare the cameras the answer showed with `expected_cameras` in `configs/eval_questions.yaml`. Rewriting the sheet reads that file again, so changing a list updates the scores without another model run. A question with no list stays blank. Fill in `correctness_1_to_5`, `clarity_1_to_5`, and `notes` by hand. Regenerating the sheet keeps those three columns.

- **Correctness (1–5):** 5 means every claim matches the frames the answer showed, and nothing it says is missing from the question's scope. 1 means it describes something the frames do not show.
- **Clarity (1–5):** 5 means a reader can act on the answer without re-reading it. 1 means it is hard to follow or repeats itself.

## Tests

```bash
make test
```

Default tests mock external HTTP; no live network required.

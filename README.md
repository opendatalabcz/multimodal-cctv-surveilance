# CCTV agent

A FastAPI chat API and a React UI for looking at configured CCTV stills. The model runs a custom Azure function-calling loop: it fetches frames, then finishes the turn by calling `submit_answer`. The UI talks to the API over `/api` only.

Runtime detail is in [docs/AGENT.md](docs/AGENT.md).

## Catalog

Cameras are grouped **sector → location → camera**. A camera is available only when the sector, the location, and the camera are all enabled.

The committed catalog has **26 cameras** in three sectors:

| Sector | Locations | Cameras |
| --- | --- | --- |
| Prague | 13 | 21 stills from the city camera portal |
| Japan | Tokachi-Obihiro, Tokyo Airport | 2 YouTube livestreams |
| Namibia | Desert, Small Pond, River | 3 YouTube livestreams |

Prague locations: Charles Bridge (2), Holešovičky (2), Budějovická (1), Nuselský most (2), Barrandovský most (2), Hybernská (1), Bělocerkevská (1), Ječná (1), Mariánské náměstí (1), Argentinská (3), Strahovský tunel (2), Tunel Mrázovka (2), Náměstí Kinských (1).

A Prague camera id is `{location_id}_{portal id}` and its name is that portal id, for example `charles_bridge_101200` / `101200`. A livestream id ends in `_live`, for example `tokachi_obihiro_live`.

## Config

| File | What it holds |
| --- | --- |
| `configs/cameras.yaml` | Committed sectors, locations, and cameras |
| `configs/cameras.local.yaml` | Gitignored camera edits, additions, and removals |
| `configs/agent.yaml` | Committed model catalog and default tool flags |
| `configs/agent.local.yaml` | Gitignored model, reasoning, verbosity, and tool toggles |

`GET/PUT /api/config` merges each committed file with its overlay. The Config panel writes overlays only. Secrets stay in the environment.

## Chat

- The header selects the model. The catalog default is GPT-5.6 Luna. GPT-4o and GPT-6 Astra are also listed. Luna and Astra can set reasoning effort and verbosity; GPT-4o cannot.
- `list_cameras` and `get_camera_image` are always available. One image call takes every matching camera, up to 16 frames.
- Optional tools follow three independent toggles: `internet` (DuckDuckGo), `weather` (Open-Meteo), and `maps` (OpenStreetMap Nominatim). They apply on the next message.
- A turn ends only when the model calls `submit_answer` with the visible markdown, the camera ids to show, and up to three follow-up questions.
- Conversations live in memory and reset when the API stops. Each turn also appends a line to `logs/chat_turns.jsonl`. Langfuse tracing is off unless `LANGFUSE_ENABLED` and both Langfuse keys are set.

External services are public demo APIs without an uptime guarantee.

## Run locally

```bash
make install_dev
make up
```

`make install_dev` installs the Python package (including pytest) and the frontend dependencies. `make up` starts the API on port 8000 and the UI on port 5173. The UI proxies `/api` to the API.

`make api` and `make ui` start one process. `make help` lists every target.

## Tests

```bash
make test
```

Default tests mock external HTTP; no live network required.

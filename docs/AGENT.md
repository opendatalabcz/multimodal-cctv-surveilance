# CCTV agent runtime

This project uses a **custom Azure OpenAI function-calling loop**, not [Deep Agents](https://docs.langchain.com/oss/python/deepagents/overview) (LangGraph). Deep Agents is a harness for long-running work (planning files, a virtual filesystem, subagents, summarization). Here the job is: read configured cameras, fetch a still, show it to the vision model, answer in chat.

Stay on this loop because:

- Frames are injected as JPEG parts after a tool returns a file path. LangChain-style tool results are usually text; we would still custom-wire vision.
- Azure is already called with `api-key` headers in `cctv.utils.azure`.
- The React UI talks only to FastAPI. Swapping the agent runtime would not change the HTTP contract.

Revisit Deep Agents only if you need long research traces, parallel subagents, or LangSmith as a thesis chapter. Tools are registered in one place so fetch code would not need a rewrite.

## Layout

| Piece | Role |
| --- | --- |
| `frontend/` | React chat + config panel |
| `src/cctv/api/` | FastAPI: config, conversations, image files |
| `src/cctv/analysis/azure_vision.py` | `chat_with_tools` loop |
| `src/cctv/tools/` | Tool schemas + executors |
| `configs/agent.yaml` | Committed camera catalog and default tool flags |
| `configs/agent.local.yaml` | Gitignored overlay: toggles, extra/edited cameras |
| `src/cctv/fetch/image_source.py` | Low-level `get_image(source)` (URLs, Prague ids, YouTube live) |

```
Config panel --> agent.local.yaml overlay on agent.yaml
Chat --> FastAPI run_chat_turn --> chat_with_tools
chat_with_tools --> enabled tools for this turn (cameras + optional external)
get_camera_image --> merged config --> fetch.get_image --> JPEG on disk
JPEG --> VLM (injected image part) and UI (/api/images/...)
```

## Config (`configs/agent.yaml` + `configs/agent.local.yaml`)

`configs/agent.yaml` is the committed catalog (demo cameras, default flags). `GET/PUT /api/config` merges that with gitignored `configs/agent.local.yaml`. The Config panel only writes the overlay: tool toggles, extra cameras, edits, and removals. Updating the catalog in git still applies unless the overlay overrides the same camera id.

```yaml
cameras:
  - id: charles_bridge
    name: Charles Bridge
    lat: 50.0865      # optional
    lon: 14.4119
    source: "https://.../cameras/101200/image"  # GET URL or YouTube live URL
tools:
  internet: false   # Internet search (web_search via DuckDuckGo)
  weather: false    # Open-Meteo measured/forecast data
  maps: false       # OpenStreetMap Nominatim place search / reverse geocode
```

Legacy overlays may still contain `google_maps`; it is loaded as `maps`. Turning `internet` on alone does **not** enable weather.

`GET` returns the merged config. Tool toggles take effect on the **next chat message** without restarting the API.

If a place is missing, the agent should tell the user to add it in the Config panel (name, optional GPS, source). It must not invent URLs.

## Camera-first routing

The system prompt (`src/cctv/config/prompt.py`) instructs the model to:

- Fetch **all configured cameras** that match a named place (by name or GPS area), not a single random sample.
- For questions with **no location**, sample **one camera per distinct place** (group by rounded GPS; missing GPS counts as its own place).
- Prefer a **soft cap of ~10 images** per turn; allow more when a place-wide question needs it.
- Describe **visible** conditions from camera frames first.
- Use `get_weather` only when the Weather toggle is on, and clearly label measured/forecast data vs camera-observed conditions.
- Use `web_search` for news/context when Internet search is on — **not** as a weather API.
- Never claim Internet, weather, or map capabilities when those toggles are off.

`run_chat_turn` reloads merged config before every user message and passes `max_tool_rounds=16` so a generous camera batch plus optional external calls can complete.

## Model-facing tools

Tools exposed to Azure depend on the current toggles (`cctv.tools.tool_schemas_for_config`):

| Name | When enabled | Effect |
| --- | --- | --- |
| `list_cameras` | always | JSON list of id, name, GPS, source, source_type from YAML |
| `get_camera_image` | always | Resolves YAML `source`, calls fetch `get_image`, returns metadata + JPEG path |
| `web_search` | `internet` | Up to 5 DuckDuckGo text results (title, URL, snippet) via `ddgs` |
| `get_weather` | `weather` | Open-Meteo current conditions + 3-day forecast (coordinates or place name) |
| `search_map` | `maps` | Nominatim place search (≤5 results) |
| `reverse_geocode` | `maps` | Nominatim reverse lookup for coordinates |

All executors are registered in `src/cctv/tools/__init__.py`. Only enabled schemas are sent to Azure; absence from the schema list is the capability gate.

Low-level `get_image(source)` remains as **implementation** (and is registered for notebooks/tests). It is not in the default model tool list.

### External service limits (demo / research grade)

These are free public services without uptime guarantees:

| Service | Module | Limits / notes |
| --- | --- | --- |
| DuckDuckGo (`ddgs`) | `web_search.py` | Max 5 results; empty/rate-limited responses return a tool error |
| Open-Meteo | `weather.py` | No API key; geocoding via Open-Meteo search API |
| Nominatim | `maps.py` | Identifying User-Agent, in-memory cache (~1 h), serialized ≤1 req/s |

External failures return a tool result (not a chat crash) so the model can explain that the source was unavailable.

After `get_camera_image` succeeds, `chat_with_tools` appends a user message containing the JPEG so the VLM can see the frame. FastAPI copies those paths to `imageUrls` like `/api/images/...` for the chat UI. Do not put large base64 blobs in the transcript JSON.

## How to add a tool

1. Add `YOUR_TOOL` schema and `execute_your_tool(arguments) -> { "tool_content": str, "image_path": str | None }` in `src/cctv/tools/`.
2. `register_tool(YOUR_TOOL, execute_your_tool)` in `src/cctv/tools/__init__.py`.
3. Wire the name into `tool_names_for_config` in `registry.py` if it is toggle-gated, or `_BASE_NAMES` if always on.
4. Mention it in `build_system_prompt` if the model needs extra policy.
5. Add a unit test that calls `execute_tool("your_tool", ...)` with HTTP mocked.

The chat loop already dispatches by name and injects any `image_path`.

## HTTP API (chat)

- `GET/PUT /api/config` — `tools`: `{ "internet": bool, "weather": bool, "maps": bool }`
- `POST /api/conversations`
- `GET /api/conversations/{id}`
- `POST /api/conversations/{id}/messages` with `{ "content": "..." }` — full transcript after the turn
- `GET /api/images/{relative-path}` — JPEG under the data directory only

Conversations are in memory and reset when the API process stops. There is no streaming.

## Run

From the Python project root (`Project/multimodal-cctv-surveilance`):

```bash
uv sync
uv run cctv-api
# or: uv run uvicorn cctv.api.app:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to port 8000. Set Azure OpenAI env vars for the API process.

## Tests

Default pytest uses mocked HTTP — no live network:

```bash
uv run pytest
```

## Out of scope

- Deep Agents / LangGraph
- Typed clarifying-question protocol
- Auth, Docker, conversation persistence, streaming
- Turn-by-turn routing / navigation (Nominatim is place context only)

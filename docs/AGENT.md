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
chat_with_tools --> list_cameras / get_camera_image
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
  internet: false
  google_maps: false
```

```yaml
cameras:
  - id: charles_bridge
    name: Charles Bridge
    lat: 50.0865      # optional
    lon: 14.4119
    source: "https://.../cameras/101200/image"  # GET URL or YouTube live URL
tools:
  internet: false
  google_maps: false
```

`GET` returns the merged config. Internet and Google Maps flags are **prompt text only**; they are not tools yet. Do not claim those capabilities in answers when they are disabled.

If a place is missing, the agent should tell the user to add it in the Config panel (name, optional GPS, source). It must not invent URLs.

## Model-facing tools

Default tools passed to Azure (`cctv.tools.default_tool_schemas()`):

| Name | Arguments | Effect |
| --- | --- | --- |
| `list_cameras` | none | JSON list of id, name, GPS, source, source_type from YAML |
| `get_camera_image` | `camera`: id or display name (case-insensitive) | Resolves YAML `source`, calls fetch `get_image`, returns metadata + JPEG path |

Low-level `get_image(source)` remains as **implementation** (and is registered for notebooks/tests). It is not in the default model tool list.

After `get_camera_image` succeeds, `chat_with_tools` appends a user message containing the JPEG so the VLM can see the frame. FastAPI copies those paths to `imageUrls` like `/api/images/...` for the chat UI. Do not put large base64 blobs in the transcript JSON.

## How to add a tool

1. Add `YOUR_TOOL` schema and `execute_your_tool(arguments) -> { "tool_content": str, "image_path": str | None }` in `src/cctv/tools/`.
2. `register_tool(YOUR_TOOL, execute_your_tool)` in `src/cctv/tools/__init__.py`.
3. Include the name in `_DEFAULT_NAMES` in `registry.py` if the model should see it.
4. Mention it in `build_system_prompt` if the model needs extra policy.
5. Add a unit test that calls `execute_tool("your_tool", ...)`.

The chat loop already dispatches by name and injects any `image_path`.

## HTTP API (chat)

- `GET/PUT /api/config`
- `POST /api/conversations`
- `GET /api/conversations/{id}`
- `POST /api/conversations/{id}/messages` with `{ "content": "..." }` — full transcript after the turn
- `GET /api/images/{relative-path}` — JPEG under the data directory only

Conversations are in memory and reset when the API process stops. There is no streaming.

## Run

From the Python project root (`Project/multimodal-cctv-surveilance`):

```bash
uv run cctv-api
# or: uv run uvicorn cctv.api.app:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to port 8000. Set Azure OpenAI env vars for the API process.

## Out of scope

- Deep Agents / LangGraph
- Real web search or Google Maps tools
- Typed clarifying-question protocol
- Auth, Docker, conversation persistence, streaming

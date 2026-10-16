# `cctv` package

FastAPI serves the React UI. A chat turn loads config, runs the Azure tool loop, fetches stills, and stores the answer. Runtime behavior is in [docs/AGENT.md](../../docs/AGENT.md).

| Package | What lives here |
| --- | --- |
| `api/` | HTTP. `cli.py` starts `cctv-api`. `app.py` is the FastAPI app. `chat.py` runs one turn, `stream.py` sends progress as SSE, `store.py` keeps conversations in memory, `schemas.py` is the request and response models, `turn_log.py` appends `logs/chat_turns.jsonl`. |
| `analysis/` | The model loop. `azure_vision.py` is `chat_with_tools` and the no-tools `analyze_images` call. `camera_metadata.py` writes a camera's scene description. `citations.py` keeps fetched frames and picks the ones `submit_answer` shows. |
| `tools/` | One module per tool: schema plus executor, registered in `__init__.py`. Always on: `list_cameras`, `get_camera`, `submit_answer`. Optional: `web_search`, `weather`, `maps`. `get_image.py` fetches a still for those tools and is not offered to the model. `registry.py` decides which schemas Azure sees. |
| `config/` | Catalog types in `models.py`. `agent_yaml.py` loads and saves `configs/cameras.yaml` and `configs/agent.yaml` plus their overlays. `effective.py` applies the sector, location, and camera toggles. `prompt.py` builds the system prompt and the welcome message. |
| `fetch/` | `image_source.py` accepts a URL, a Prague id, or a YouTube live link. `decoder.py` downloads one Prague still. `youtube.py` grabs one livestream frame. `sources.py` classifies the source. `http.py` is the HTTP client. Prague stills are saved under `camera_images/prague/{portal id}/`. |
| `observability/` | Optional Langfuse tracing. Off unless the Langfuse env vars are set. `tracing.py` opens the turn, generation, and tool spans. `sanitize.py` strips secrets before export. `usage.py` normalizes token counts. |
| `utils/` | `azure.py` reads the Azure OpenAI env vars. `paths.py` finds the project root, the data directory, and image folders. |

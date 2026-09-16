# CCTV agent

Python package for multimodal CCTV analysis, with a FastAPI chat API and a React UI.

## Docs

- [Agent runtime, camera tools, and how to extend them](docs/AGENT.md)

## Run locally

API (from this directory):

```bash
uv run cctv-api
# or: uv run uvicorn cctv.api.app:app --reload --port 8000
```

UI:

```bash
cd frontend
npm install
npm run dev
```

The Vite app is at http://localhost:5173 and proxies `/api` to port 8000. Azure OpenAI credentials come from the environment (never from the frontend).

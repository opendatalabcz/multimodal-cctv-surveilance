# Agent notes

FastAPI package in `src/cctv/`, React/Vite UI in `frontend/`. The only coupling is HTTP (`/api`).

## Run

API (port 8000):

```bash
uv sync
uv run cctv-api
```

UI (port 5173, proxies `/api` to 8000):

```bash
cd frontend
npm install
npm run dev
```

Tests (mocked HTTP, no live network): `uv run pytest`.

## Config and secrets

- Committed camera catalog: [`configs/cameras.yaml`](configs/cameras.yaml). Local overlay: `configs/cameras.local.yaml`.
- Committed agent settings (models, tool flags): [`configs/agent.yaml`](configs/agent.yaml). Local overlay: `configs/agent.local.yaml`.
- The Config panel writes the overlays only.
- Azure OpenAI and other secrets stay in the environment / FastAPI. Never put keys in the frontend.

## Runtime

Read [`docs/AGENT.md`](docs/AGENT.md) before changing the Azure tool loop, camera catalog, or tool registration. This is a custom Azure function-calling loop, not Deep Agents / LangGraph.

## Git

Develop on `dev`. Notebooks and old experiment data live on branch `experiments` and tag `archive/experiments`.

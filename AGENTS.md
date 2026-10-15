# Agent notes

FastAPI package in `src/cctv/`, React/Vite UI in `frontend/`. The only coupling is HTTP (`/api`).

## Run

```bash
make install_dev   # Python package (including pytest) and frontend deps
make up            # API :8000 and UI :5173
make api           # API only
make ui            # UI only
make test          # pytest, mocked HTTP, no live network
```

The UI proxies `/api` to port 8000.

## Config and secrets

- Committed camera catalog: [`configs/cameras.yaml`](configs/cameras.yaml). Local overlay: `configs/cameras.local.yaml`.
- Committed agent settings (models, tool flags): [`configs/agent.yaml`](configs/agent.yaml). Local overlay: `configs/agent.local.yaml`.
- The Config panel writes the overlays only.
- Azure OpenAI and other secrets stay in the environment / FastAPI. Never put keys in the frontend.

## Runtime

Read [`docs/AGENT.md`](docs/AGENT.md) before changing the Azure tool loop, camera catalog, or tool registration. This is a custom Azure function-calling loop, not Deep Agents / LangGraph.

## Git

Develop on `dev`. Notebooks and old experiment data live on branch `experiments` and tag `archive/experiments`.

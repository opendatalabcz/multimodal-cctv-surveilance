# Agent notes

FastAPI package in `src/cctv/`, React/Vite UI in `frontend/`. The only coupling is HTTP (`/api`).

## Run

```bash
make install_dev   # Python package (including pytest) and frontend deps
make up            # API :8000 and UI :5173
make api           # API only
make ui            # UI only
make test          # pytest, mocked HTTP, no live network
make eval          # one fresh chat per question, model, and verbosity
```

The UI proxies `/api` to port 8000. `make eval` writes `outputs/end_to_end_eval/` and does not change `configs/agent.yaml`. It needs Azure credentials and reachable cameras. `--screenshot` (`uv run cctv-eval --screenshot`) also needs `make up` and `uv run playwright install chromium`. Questions live in `configs/eval_questions.yaml`.

## Config and secrets

- Camera catalog, including scene analysis: [`configs/cameras.yaml`](configs/cameras.yaml).
- Agent settings (models, selected model, tool flags): [`configs/agent.yaml`](configs/agent.yaml).
- Evaluation questions: [`configs/eval_questions.yaml`](configs/eval_questions.yaml).
- The Config panel writes those two files.
- Azure OpenAI and other secrets stay in the environment / FastAPI. Never put keys in the frontend.

## Runtime

Read [`docs/AGENT.md`](docs/AGENT.md) before changing the Azure tool loop, camera catalog, or tool registration. This is a custom Azure function-calling loop, not Deep Agents / LangGraph.

## Git

Develop on `dev`. Notebooks and old experiment data live on branch `experiments` and tag `archive/experiments`.

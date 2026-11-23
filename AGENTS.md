# Agent notes

FastAPI package in `src/cctv/`, React/Vite UI in `frontend/`. The only coupling is HTTP (`/api`).

## Run

```bash
make install_dev   # Python package (including pytest) and frontend deps
make up            # API :8000 and UI :5173
make api           # API only
make ui            # UI only
make test          # pytest, mocked HTTP, no live network
make eval          # one fresh chat per question and enabled model at medium verbosity; Terra also runs reasoning low and high
make eval-report   # rewrite grading.csv for the latest run under outputs/end_to_end_eval/, no model calls
make eval-charts   # PNG charts and summary.csv in the latest run's charts/ folder, no model calls
uv run cctv-eval --charts --all-runs   # pool every run into outputs/charts/
```

The UI proxies `/api` to port 8000. `make eval` starts a new folder `outputs/end_to_end_eval/<local time>/` and does not change `configs/agent.yaml`. `--run <id>` continues that folder. It needs Azure credentials and reachable cameras. `--screenshot` (`uv run cctv-eval --screenshot`) also needs `make up` and `uv run playwright install chromium`. Questions live in `configs/eval_questions.yaml`.

## Config and secrets

- Camera catalog, including scene analysis: [`configs/cameras.yaml`](configs/cameras.yaml).
- Agent settings (models, which of those are enabled, selected model, tool flags): [`configs/agent.yaml`](configs/agent.yaml).
- Evaluation questions: [`configs/eval_questions.yaml`](configs/eval_questions.yaml).
- The Config panel writes those two files.
- Azure OpenAI, OpenRouter, and other secrets stay in the environment / FastAPI. Never put keys in the frontend.

## Runtime

Read [`docs/AGENT.md`](docs/AGENT.md) before changing the Azure tool loop, camera catalog, or tool registration. This is a custom Azure function-calling loop, not Deep Agents / LangGraph.

## Git

Develop on `dev`. Notebooks and old experiment data live on branch `experiments` and tag `archive/experiments`.

.PHONY: help install_dev api ui up run test eval eval-report eval-charts

FRONTEND := frontend

help:
	@echo "install_dev  Install Python (uv, including pytest) and frontend npm deps"
	@echo "up, run      Start API :8000 and UI :5173 together"
	@echo "api          Start FastAPI only"
	@echo "ui           Start Vite only"
	@echo "test         Run pytest (mocked HTTP)"
	@echo "eval         Start a new dated eval run under outputs/end_to_end_eval/"
	@echo "eval-report  Rewrite grading.csv for the latest eval run (no model calls)"
	@echo "eval-charts  Write charts and summary.csv for the latest eval run (no model calls)"

install_dev:
	uv sync --group dev
	npm install --prefix $(FRONTEND)

api:
	uv run cctv-api

ui:
	npm run dev --prefix $(FRONTEND)

up:
	$(MAKE) -j2 api ui

run: up

test:
	uv run pytest

eval:
	uv run cctv-eval

eval-report:
	uv run cctv-eval --report

eval-charts:
	uv run cctv-eval --charts

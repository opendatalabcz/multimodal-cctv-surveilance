.PHONY: help install_dev api ui up run test

FRONTEND := frontend

help:
	@echo "install_dev  Install Python (uv, including pytest) and frontend npm deps"
	@echo "up, run      Start API :8000 and UI :5173 together"
	@echo "api          Start FastAPI only"
	@echo "ui           Start Vite only"
	@echo "test         Run pytest (mocked HTTP)"

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

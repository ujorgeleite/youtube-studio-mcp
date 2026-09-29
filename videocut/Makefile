VENV   := .venv
PYTHON := $(VENV)/bin/python
PIP    := $(PYTHON) -m pip

.DEFAULT_GOAL := help
.PHONY: help install test test-verbose ui check-ffmpeg clean

help: ## List available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

$(PYTHON):
	python3 -m venv $(VENV)
	$(PIP) install -q --upgrade pip

install: $(PYTHON) ## Create the venv and install dependencies
	$(PIP) install -q -r requirements.txt

test: ## Run the tests (no model downloads, no real inference)
	$(PYTHON) -m pytest -q

test-verbose: ## Run the tests with full output
	$(PYTHON) -m pytest -v

ui: check-ffmpeg ## Launch the VideoCut interface (http://localhost:8090)
	$(PYTHON) ui/app.py

check-ffmpeg: ## Verify ffmpeg/ffprobe are installed on the system
	@command -v ffmpeg >/dev/null 2>&1 || { echo "ffmpeg não encontrado no PATH (brew install ffmpeg)"; exit 1; }
	@command -v ffprobe >/dev/null 2>&1 || { echo "ffprobe não encontrado no PATH"; exit 1; }
	@ffmpeg -version | head -1

clean: ## Remove venv and caches
	rm -rf $(VENV) .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

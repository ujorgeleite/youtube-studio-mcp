VENV   := .venv
PYTHON := $(VENV)/bin/python
PIP    := $(PYTHON) -m pip

INPUT   ?= ./clipes_brutos
FORMAT  ?= qualidade-de-vida
OUTPUT  ?= ./stringout.mp4

.DEFAULT_GOAL := help
.PHONY: help install test test-verbose run dry-run check-ffmpeg lint clean

help: ## List available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

$(PYTHON):
	python3 -m venv $(VENV)
	$(PIP) install -q --upgrade pip

install: $(PYTHON) ## Create the venv and install dependencies
	$(PIP) install -q -r requirements.txt

test: ## Run the tests (no LLM, no Whisper)
	$(PYTHON) -m pytest -q

test-verbose: ## Run the tests with full output
	$(PYTHON) -m pytest -v

run: check-ffmpeg ## Run the full pipeline (INPUT=... FORMAT=... OUTPUT=...)
	$(PYTHON) run.py --input "$(INPUT)" --format "$(FORMAT)" --output "$(OUTPUT)"

dry-run: check-ffmpeg ## Assemble-only demo from the fixture cut-list (no LLM/Whisper)
	$(PYTHON) run.py --dry-run --output "$(OUTPUT)"

check-ffmpeg: ## Verify ffmpeg is installed on the system
	@command -v ffmpeg >/dev/null 2>&1 || { echo "ffmpeg não encontrado no PATH (brew install ffmpeg)"; exit 1; }
	@ffmpeg -version | head -1

clean: ## Remove venv, caches and pipeline outputs
	rm -rf $(VENV) .pytest_cache stringout.mp4 *.cut-list.json
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

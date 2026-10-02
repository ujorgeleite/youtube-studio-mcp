VENV   := .venv
PYTHON := $(VENV)/bin/python
PIP    := $(PYTHON) -m pip

INPUT  ?= ./raw
EDIT   ?= ./edicao-final.mp4
MODELS ?= qwen3-vl-4b,qwen3-vl-8b

.DEFAULT_GOAL := help
.PHONY: help install doctor models test test-verbose ui analyze compare benchmark check-ffmpeg clean

help: ## List available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

$(PYTHON):
	python3 -m venv $(VENV)
	$(PIP) install -q --upgrade pip

install: $(PYTHON) ## Create the venv and install dependencies
	$(PIP) install -q -r requirements.txt

doctor: ## Check ffmpeg, dependencies, memory and cached models
	$(PYTHON) cli.py doctor

models: ## Download Whisper and the default vision model with progress (MODELS=... optional)
	$(PYTHON) cli.py models $(if $(filter command line,$(origin MODELS)),--models "$(MODELS)")

test: ## Run the tests (no model downloads, no real inference)
	$(PYTHON) -m pytest -q

test-verbose: ## Run the tests with full output
	$(PYTHON) -m pytest -v

ui: check-ffmpeg ## Launch the VideoCut interface (http://localhost:8090)
	$(PYTHON) ui/app.py

analyze: check-ffmpeg ## Analyze a folder without the UI (INPUT=...)
	$(PYTHON) cli.py analyze "$(INPUT)"

compare: check-ffmpeg ## Compare the proposal with your finished edit (INPUT=... EDIT=...)
	$(PYTHON) cli.py compare "$(INPUT)" "$(EDIT)"

benchmark: check-ffmpeg ## Measure vision models on your takes (INPUT=... MODELS=...)
	$(PYTHON) cli.py benchmark "$(INPUT)" --models "$(MODELS)"

check-ffmpeg: ## Verify ffmpeg/ffprobe are installed on the system
	@command -v ffmpeg >/dev/null 2>&1 || { echo "ffmpeg não encontrado no PATH (brew install ffmpeg)"; exit 1; }
	@command -v ffprobe >/dev/null 2>&1 || { echo "ffprobe não encontrado no PATH"; exit 1; }
	@ffmpeg -version | head -1

clean: ## Remove venv and caches
	rm -rf $(VENV) .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

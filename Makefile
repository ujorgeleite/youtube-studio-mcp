VENV   := .venv
PYTHON := $(VENV)/bin/python
BIN    := $(VENV)/bin/youtube-studio-mcp

.DEFAULT_GOAL := help
.PHONY: help install test test-verbose shell serve auth overview refresh mcp-add clean clean-cache

help: ## List available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

$(PYTHON):
	python3 -m venv $(VENV)
	$(PYTHON) -m pip install -q --upgrade pip

install: $(PYTHON) ## Create the venv and install the project + dev deps
	$(PYTHON) -m pip install -q -e ".[dev]"

test: ## Run the tests
	$(PYTHON) -m pytest -q

test-verbose: ## Run the tests with full output
	$(PYTHON) -m pytest -v

shell: ## Open the interactive menu (Tab completion)
	$(BIN) shell

serve: ## Run the MCP server over stdio
	$(BIN) serve

auth: ## Log in with Google (opens the browser)
	$(BIN) auth

overview: ## Print the channel overview (cached)
	$(BIN) overview

refresh: ## Print the channel overview bypassing the cache
	$(BIN) overview --refresh

mcp-add: ## Register this server in Claude Code
	claude mcp add youtube-studio -- "$(CURDIR)/$(BIN)" serve

clean-cache: ## Delete the local SQLite cache
	rm -f "$${YTS_DATA_DIR:-$$HOME/.youtube-studio-mcp}/cache.db"

clean: ## Remove venv and build/test artifacts
	rm -rf $(VENV) .pytest_cache src/*.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

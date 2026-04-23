UV = uv
NPM = npm
DOCKER_COMPOSE = docker compose

PYTHON_SRC = packages/autods/src apps/server/src apps/cli/src
PYTHON_TESTS = packages/autods/tests apps/server/tests apps/cli/tests
FRONTEND_DIR = apps/frontend
COGNEE_COMPOSE_FILE = docker/docker-compose-cognee.yml

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show available commands
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z0-9_-]+:.*##/ { printf "  %-20s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

.PHONY: install
install: ## Sync the Python workspace
	$(UV) sync --all-packages

.PHONY: install-all
install-all: install frontend-install ## Sync Python workspace and frontend deps

.PHONY: update
update: ## Refresh the workspace lockfile and environment
	$(UV) sync --all-packages --upgrade

.PHONY: test
test: ## Run the Python test suite
	$(UV) run pytest

.PHONY: test-core
test-core: ## Run core package tests
	$(UV) run pytest packages/autods/tests

.PHONY: test-server
test-server: ## Run server app tests
	$(UV) run pytest apps/server/tests

.PHONY: test-cli
test-cli: ## Run CLI app tests
	$(UV) run pytest apps/cli/tests

.PHONY: lint
lint: ## Run ruff checks across Python workspace code
	$(UV) run ruff check $(PYTHON_SRC) $(PYTHON_TESTS)

.PHONY: format
format: ## Format Python workspace code
	$(UV) run ruff format $(PYTHON_SRC) $(PYTHON_TESTS)

.PHONY: format-check
format-check: ## Check Python formatting
	$(UV) run ruff format --check $(PYTHON_SRC) $(PYTHON_TESTS)

.PHONY: mypy
mypy: ## Run mypy across Python workspace code
	$(UV) run mypy $(PYTHON_SRC)

.PHONY: check
check: lint mypy test ## Run lint, type-check, and tests

.PHONY: quality
quality: check ## Run the required quality gate

.PHONY: clean
clean: ## Remove Python and frontend build artifacts
	rm -rf .coverage .mypy_cache .pytest_cache .ruff_cache htmlcov
	rm -rf $(FRONTEND_DIR)/.next
	find packages apps -type d -name __pycache__ -prune -exec rm -rf {} +
	find packages apps -name '*.pyc' -delete

.PHONY: frontend-install
frontend-install: ## Install frontend dependencies
	cd $(FRONTEND_DIR) && $(NPM) install

.PHONY: frontend-dev
frontend-dev: ## Run the frontend dev server
	cd $(FRONTEND_DIR) && $(NPM) run dev

.PHONY: frontend-lint
frontend-lint: ## Run the frontend linter
	cd $(FRONTEND_DIR) && $(NPM) run lint

.PHONY: frontend-build
frontend-build: ## Build the frontend
	cd $(FRONTEND_DIR) && $(NPM) run build

.PHONY: server-dev
server-dev: ## Run the API server with default settings
	$(UV) run autods-web

.PHONY: cli-help
cli-help: ## Print CLI help
	$(UV) run autods --help

.PHONY: cognee-up
cognee-up: ## Start Cognee services
	$(DOCKER_COMPOSE) -f $(COGNEE_COMPOSE_FILE) --profile "*" up -d

.PHONY: cognee-down
cognee-down: ## Stop Cognee services
	$(DOCKER_COMPOSE) -f $(COGNEE_COMPOSE_FILE) down

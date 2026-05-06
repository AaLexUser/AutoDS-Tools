python-src := "apps/server/src apps/cli/src"
python-tests := "apps/server/tests apps/cli/tests"
frontend-dir := "apps/frontend"
cognee-compose-file := "docker/docker-compose-cognee.yml"
docker-compose-file := "docker/docker-compose.yml"
docker-env-file := "docker/.env"

# Run ruff linter
lint:
    uv run ruff check {{python-src}} {{python-tests}}

# Run ruff formatter (check only)
fmt-check:
    uv run ruff format --check {{python-src}} {{python-tests}}

# Run ruff formatter (write changes)
fmt:
    uv run ruff format {{python-src}} {{python-tests}}

# Auto-fix lint issues
lint-fix:
    uv run ruff check --fix {{python-src}} {{python-tests}}

# Run ty type checker
ty:
    uv run ty check {{python-src}} {{python-tests}}

# Sync the Python workspace
install:
    uv sync --all-packages

# Refresh the workspace lockfile and environment
update:
    uv sync --all-packages --upgrade

# Run the Python test suite
test *FLAGS:
    uv run pytest -v {{FLAGS}}

# Run core package tests
test-core:
    uv run pytest packages/autods/tests

# Run pygrad package tests
test-pygrad:
    uv run pytest packages/pygrad/tests

# Run server app tests
test-server:
    uv run pytest apps/server/tests

# Run CLI app tests
test-cli:
    uv run pytest apps/cli/tests

# Run all checks
check:
    just lint
    just fmt-check
    just ty
    just test

# Run the required quality gate
quality:
    just check

# Remove Python and frontend build artifacts
clean:
    rm -rf .coverage .mypy_cache .pytest_cache .ruff_cache .ty_cache htmlcov
    rm -rf {{frontend-dir}}/.next
    find packages apps -type d -name __pycache__ -prune -exec rm -rf {} +
    find packages apps -name '*.pyc' -delete
    find packages -type d -name '*.egg-info' -prune -exec rm -rf {} +

# Install frontend dependencies
frontend-install:
    cd {{frontend-dir}} && npm install

# Run the frontend dev server
frontend-dev:
    cd {{frontend-dir}} && npm run dev

# Run the frontend linter
frontend-lint:
    cd {{frontend-dir}} && npm run lint

# Build the frontend
frontend-build:
    cd {{frontend-dir}} && npm run build

# Run the API server with default settings
server-dev:
    uv run autods-web

# Print CLI help
cli-help:
    uv run autods --help

# Run the pygrad CLI
pygrad-cli *FLAGS:
    uv run pygrad {{FLAGS}}

# Start Cognee services
cognee-up:
    docker compose -f {{cognee-compose-file}} --profile "*" up -d

# Stop Cognee services
cognee-down:
    docker compose -f {{cognee-compose-file}} down

# Validate the VPS deployment compose file
docker-config:
    docker compose --env-file {{docker-env-file}} -f {{docker-compose-file}} config

# Build and start the VPS deployment stack
docker-up *FLAGS:
    docker compose --env-file {{docker-env-file}} -f {{docker-compose-file}} up -d --build {{FLAGS}}

# Stop the VPS deployment stack
docker-down:
    docker compose --env-file {{docker-env-file}} -f {{docker-compose-file}} down

# Tail logs for the VPS deployment stack
docker-logs *FLAGS:
    docker compose --env-file {{docker-env-file}} -f {{docker-compose-file}} logs -f {{FLAGS}}

cloc:
    cloc {{python-src}} {{python-tests}} {{frontend-dir}} --exclude-dir=node_modules,.git,__pycache__,.next,.venv,.ruff_cache,.pytest_cache,.mypy_cache,.ty_cache,dist,build,htmlcov,.turbo,coverage,package.json,package-lock.json,tsconfig.json

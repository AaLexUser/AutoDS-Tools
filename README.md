# AutoDS-Tools

![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)
![License](https://img.shields.io/badge/license-BSD%203--Clause-green.svg)
![LangGraph](https://img.shields.io/badge/built%20with-LangGraph-orange.svg)

AutoDS-Tools is an early-stage AutoML agent system built as a monorepo. The codebase is split into small workspace packages and apps: reusable Python libraries live in `packages/`, runnable entry points live in `apps/`, and service assets live in `docker/`.

## Demo

[Watch the Video on YouTube](https://youtu.be/H_88VTaxsfs)

## Workspace Layout

```text
AutoDS-Tools/
├── apps/
│   ├── cli/          # autods CLI entry point
│   ├── frontend/     # Next.js UI
│   └── server/       # FastAPI backend
├── packages/
│   └── autods/       # core agent library, including notebook execution
├── docker/           # local compose assets
├── pyproject.toml    # uv workspace root
└── Makefile
```

Module-specific notes live next to each workspace member:

- [packages/autods/README.md](packages/autods/README.md)
- [apps/server/README.md](apps/server/README.md)
- [apps/cli/README.md](apps/cli/README.md)
- [apps/frontend/README.md](apps/frontend/README.md)
- [docker/README.md](docker/README.md)

## Architecture

![AutoDS-Tools Architecture](docs/images/AutoDS-Tools.png)

The main workflow is still the same:

1. Analyst explores the task and data.
2. Researcher studies relevant libraries through GRAD.
3. Planner creates an execution strategy.
4. Coder implements and debugs the solution.
5. Presenter audits and summarizes the result.

The current packaging is intentionally simple: the Python core owns both the agent logic and notebook execution, while the CLI, server, and frontend are isolated entry points.

## Prerequisites

- Python 3.12+
- `uv`
- Node.js 18+ and `npm` for the frontend
- Docker, if you want to run local support services

## Setup

### Python workspace

```bash
make install
```

That runs `uv sync --all-packages` and installs all Python workspace members into the shared workspace environment.

### Frontend

```bash
make frontend-install
```

Or manually:

```bash
cd apps/frontend
npm install
```

## Configuration

The application reads config from `~/.autods/autods_config.yaml`.

Start from the example:

```bash
mkdir -p ~/.autods
cp autods_config.yaml.example ~/.autods/autods_config.yaml
```

Minimal example:

```yaml
model_providers:
  openai:
    provider: openai
    api_key: ${OPENAI_API_KEY}

models:
  gpt_5:
    model_provider: openai
    model: gpt-5
    max_retries: 3

agents:
  autods:
    model: gpt_5
    max_steps: 50
    analyst_steps: 5
    researcher_steps: 5
    planner_steps: 5
    debugger_steps: 5
    presenter_steps: 5
```

See [autods_config.yaml.example](autods_config.yaml.example) for the fuller template.

## Running The System

### Backend

```bash
make server-dev
```

Or:

```bash
uv run autods-web
```

The API listens on `http://localhost:8000` by default.

### Frontend

```bash
make frontend-dev
```

The UI runs on `http://localhost:3000`.

The frontend uses `NEXT_PUBLIC_API_URL` and defaults to `http://localhost:8000`. Override it in `apps/frontend/.env.local` if needed.

### CLI

```bash
uv run autods --help
uv run autods chat
uv run autods exec "Solve this classification task using LightAutoML"
uv run autods resume <session-id>
```

## Common Commands

```bash
make help
make format
make lint
make mypy
make test
make check
make frontend-lint
make frontend-build
```

## GRAD

GRAD is the documentation and graph-retrieval layer used by the agent when it needs to understand external libraries. The current repository structure keeps that behavior inside the core package; it is not a separate workspace package yet.

## Status

This repository is still early-stage. The monorepo layout is intended to make future extraction and replacement easier, not to preserve old paths.

## License

See [LICENSE](LICENSE).

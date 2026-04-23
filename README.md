<div align="center">

# `AutoDS-Tools`

![Python 3.12+](https://img.shields.io/badge/python-3.12+-white.svg)
![License](https://img.shields.io/badge/license-BSD%203--Clause-white.svg)
![LangGraph](https://img.shields.io/badge/built%20with-LangGraph-white.svg)

**Multi-agent AutoDS system that can work with any DS/ML library.**

</div>

## Demo

[Watch the Video on YouTube](https://youtu.be/H_88VTaxsfs)

<a href=https://youtu.be/H_88VTaxsfs><img width="400" alt="Watch the video" src="https://github.com/user-attachments/assets/d782e3e8-2daf-460a-a635-9c1120c5f953" /></a>


## Workspace Layout

```text
AutoDS-Tools/
├── apps/
│   ├── cli/          # autods CLI entry point
│   ├── frontend/     # Next.js UI
│   └── server/       # FastAPI backend
├── packages/
│   └── autods/       # core agent library
├── docker/           # local compose assets
├── pyproject.toml    # uv workspace root
└── Makefile
```

## Architecture

![AutoDS-Tools Architecture](docs/images/AutoDS-Tools.png)

The main workflow:

1. Analyst explores the task and data.
2. Researcher studies relevant libraries through GRAD.
3. Planner creates an execution strategy.
4. Coder implements and debugs the solution.
5. Presenter audits and summarizes the result.


## Prerequisites

- Python 3.12+
- `uv`
- Node.js 18+ and `npm` for the frontend
- Docker

## Setup

### Python workspace

```bash
make install
```

That runs `uv sync --all-packages` and installs all Python workspace members into the shared workspace environment.

### Frontend

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

### Server

```bash
uv run autods-web
# or
uv run autods server
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
uv run autods server
```

CLI behavior:

- if `--server-url` or `AUTODS_SERVER_URL` is set, the CLI talks to that hosted server
- otherwise, `chat`, `exec`, and `resume` auto-start a local server on `127.0.0.1:8000` if needed
- the CLI stores a persistent principal token in `~/.autods/cli_principal_token`
- browser and CLI can share the same hosted session namespace if they use the same principal identity

Examples:

```bash
# Start an explicit local server
uv run autods server

# Run against a remote server
AUTODS_SERVER_URL=http://my-host:8000 uv run autods exec "Train a baseline model"

# Override server URL per command
uv run autods exec --server-url http://my-host:8000 "Analyze this dataset"
```


## GRAD

GRAD is the documentation and graph-retrieval layer used by the agent when it needs to understand external libraries.

For more information, visit https://github.com/AaLexUser/pygrad.

## License

See [LICENSE](LICENSE).

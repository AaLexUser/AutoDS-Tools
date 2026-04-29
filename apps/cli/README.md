# autods-cli

`autods-cli` is the command-line entry point for the project.

It wraps the core agent and exposes interactive chat, one-shot execution, session resume, and a helper command for starting the web server.

## Entry Point

```bash
uv run autods --help
```

## Main Commands

```bash
uv run autods chat
uv run autods exec "Solve this task"
uv run autods resume <session-id>
uv run autods web
```

## Commands

```bash
just cli-help
just test-cli
uv run pytest apps/cli/tests
```

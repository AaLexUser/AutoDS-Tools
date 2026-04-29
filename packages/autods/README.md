# autods

`autods` is the core Python library for the project.

It contains the reusable agent runtime, prompting, task inference, tools, session handling, configuration, and environment abstractions. It does not expose a runnable app by itself.

## Source Layout

```text
packages/autods/
├── pyproject.toml
├── src/autods/
│   ├── agents/
│   ├── callbacks/
│   ├── environments/
│   ├── prompting/
│   ├── runtime/
│   ├── sessions/
│   ├── task_inference/
│   ├── tools/
│   └── utils/
└── tests/
```

## Boundaries

- Depends on shared Python libraries only.
- Does not import the server or CLI apps.
- Owns notebook execution directly under `autods.environments`.

## Typical Work

- Add or refactor agent behavior.
- Change prompts and tool contracts.
- Adjust config loading and runtime flow.
- Add tests for core library behavior.

## Commands

```bash
just test-core
uv run pytest packages/autods/tests
```

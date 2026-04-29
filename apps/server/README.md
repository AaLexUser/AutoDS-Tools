# autods-web

`autods-web` is the FastAPI backend app.

It exposes the HTTP and WebSocket API used by the frontend and creates agent runners for interactive sessions.

## Responsibilities

- Session lifecycle over HTTP/WebSocket
- File and artifact access
- API-side tracing and streaming
- Wiring the core agent into a web interface

## Entry Point

```bash
uv run autods-web
```

Default address: `http://localhost:8000`

## Commands

```bash
just server-dev
just test-server
uv run pytest apps/server/tests
```

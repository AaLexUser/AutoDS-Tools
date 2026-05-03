# docker

This directory contains local Docker Compose assets used by the project.

Right now it includes:

- `docker-compose.yml`
- `docker-compose-cognee.yml`
- `Caddyfile`
- `.env.example`

## Commands

```bash
cp docker/.env.example docker/.env
docker compose --env-file docker/.env -f docker/docker-compose.yml config
docker compose --env-file docker/.env -f docker/docker-compose.yml up -d --build
docker compose --env-file docker/.env -f docker/docker-compose.yml down

just cognee-up
just cognee-down
```

`docker-compose.yml` is the VPS-oriented stack:

- `reverse-proxy` via Caddy
- `autods-frontend`
- `autods-server`
- `neo4j`

`docker-compose-cognee.yml` remains the smaller local support stack for existing Cognee-related workflows.

The production-style stack expects a real `docker/.env` file. Important values include:

- `PUBLIC_HOST`
- `BASIC_AUTH_USERNAME`
- `BASIC_AUTH_PASSWORD_HASH`
- `NEXT_PUBLIC_API_URL`
- `AUTODS_MODEL`
- `AUTODS_API_KEY`
- `AUTODS_BASE_URL`
- `SEARCH_BACKEND`
- `NEO4J_URI`
- `NEO4J_USERNAME`
- `NEO4J_PASSWORD`
- `LLM_PROVIDER`
- `LLM_MODEL`
- `LLM_ENDPOINT`
- `EMBEDDING_PROVIDER`
- `EMBEDDING_MODEL`
- `EMBEDDING_ENDPOINT`
- `EMBEDDING_DIMENSIONS`
- `AUTH_MODE`
- `WORKOS_CLIENT_ID`
- `WORKOS_API_KEY`
- `WORKOS_REDIRECT_URI`

The reverse proxy now enforces HTTP basic auth for the entire site, which is the
safest way to protect this demo deployment because it gates both the frontend and
the backend API. Generate the password hash with Caddy before you bring the stack
up:

```bash
docker run --rm caddy:2.10.2 caddy hash-password --plaintext 'choose-a-strong-demo-password'
```

Then set `BASIC_AUTH_USERNAME` and `BASIC_AUTH_PASSWORD_HASH` in `docker/.env`.
If you are using the shared Caddy password gate, keep `AUTH_MODE=disabled` so the
app does not expect WorkOS.

For AutoDS itself, the model runtime is configured through `AUTODS_MODEL`, `AUTODS_API_KEY`, and `AUTODS_BASE_URL`.

For `pygrad` with `SEARCH_BACKEND=neo4j-graphrag`, the `LLM_*` and `EMBEDDING_*` environment variables are part of the deployment contract. They are read directly by the `pygrad` GraphRAG integration.

If you use Ollama, do not point these endpoints at `localhost` unless Ollama is running inside the same container. In Docker, prefer a reachable network address such as an `ollama` service hostname.

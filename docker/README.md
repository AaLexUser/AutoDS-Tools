# docker

This directory contains local Docker Compose assets used by the project.

Right now it includes:

- `docker-compose-cognee.yml`

## Commands

```bash
make cognee-up
make cognee-down
```

These targets call Docker Compose against the files in this directory rather than from the repository root.

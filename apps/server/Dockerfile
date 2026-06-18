# syntax=docker/dockerfile:1.7

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    DEBIAN_FRONTEND=noninteractive

# git is required at runtime by pygrad repository cloning.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl git libffi-dev pkg-config

WORKDIR /app

COPY pyproject.toml uv.lock /app/
COPY packages/pygrad/pyproject.toml packages/pygrad/README.md /app/packages/pygrad/
COPY packages/autods/pyproject.toml packages/autods/README.md /app/packages/autods/
COPY apps/server/pyproject.toml apps/server/README.md /app/apps/server/

RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install --upgrade pip uv

RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    uv export --frozen --package autods-web --no-dev \
      --no-emit-package autods-web --no-emit-package autods --no-emit-package pygrad \
      --no-hashes --output-file /tmp/autods-server.requirements.txt \
    && uv pip install --system -r /tmp/autods-server.requirements.txt \
    && python -c "from langchain.agents import AgentState, create_agent"

COPY packages/pygrad/src /app/packages/pygrad/src
COPY packages/autods/src /app/packages/autods/src
COPY apps/server/src /app/apps/server/src

RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    uv pip install --system --no-deps /app/packages/pygrad /app/packages/autods /app/apps/server

VOLUME ["/root/.autods", "/root/.pygrad"]

EXPOSE 8000

CMD ["uvicorn", "autods_web.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "86400"]

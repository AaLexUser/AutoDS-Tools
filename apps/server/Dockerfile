FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# git is required at runtime by pygrad repository cloning.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY packages/pygrad/pyproject.toml packages/pygrad/README.md /app/packages/pygrad/
COPY packages/pygrad/src /app/packages/pygrad/src
COPY packages/autods/pyproject.toml packages/autods/README.md /app/packages/autods/
COPY packages/autods/src /app/packages/autods/src
COPY apps/server/pyproject.toml apps/server/README.md /app/apps/server/
COPY apps/server/src /app/apps/server/src

RUN pip install --upgrade pip \
    && pip install /app/packages/pygrad \
    && pip install /app/packages/autods \
    && pip install /app/apps/server

VOLUME ["/root/.autods", "/root/.pygrad"]

EXPOSE 8000

CMD ["uvicorn", "autods_web.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]


FROM python:3.12-slim

# git is required at runtime by clone_repository
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY src/ src/

RUN pip install --no-cache-dir ".[server]"

# Persistent storage for cloned repos and cognee data
VOLUME ["/root/.pygrad"]

EXPOSE 8446

CMD ["uvicorn", "pygrad.server:app", "--host", "0.0.0.0", "--port", "8446"]

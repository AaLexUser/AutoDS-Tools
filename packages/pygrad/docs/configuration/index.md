# Configuration

Configure Pygrad's LLM provider, embeddings, and storage.

## Overview

Pygrad uses [Cognee](https://github.com/topoteretes/cognee) under the hood, which supports various LLM providers and databases. Configuration is done through environment variables.

## Quick Links

<div class="grid" markdown>

<div class="card" markdown>

### [:material-server: Ollama (Local)](ollama.md)

Run with local LLMs for privacy and offline use.

</div>

<div class="card" markdown>

### [:material-cloud: OpenAI](openai.md)

Use OpenAI's GPT models and embeddings.

</div>

<div class="card" markdown>

### [:material-database: Database](database.md)

Configure PostgreSQL, Neo4j, and other backends.

</div>

</div>

## Environment Variables

All configuration is done through environment variables. You can set them directly or use a `.env` file.

### Core Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | LLM provider name | `openai` |
| `LLM_MODEL` | Model name | `gpt-4o` |
| `LLM_API_KEY` | API key | - |
| `LLM_ENDPOINT` | Custom endpoint URL | - |
| `EMBEDDING_PROVIDER` | Embedding provider | `openai` |
| `EMBEDDING_MODEL` | Embedding model name | `text-embedding-3-small` |
| `EMBEDDING_ENDPOINT` | Custom embedding endpoint | - |
| `EMBEDDING_DIMENSIONS` | Vector dimensions | `1536` |

### Storage Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VECTOR_DB_PROVIDER` | Vector database | `lancedb` |
| `DB_PROVIDER` | Relational database | `sqlite` |
| `GRAPH_DATABASE_PROVIDER` | Graph database | `networkx` |

## Configuration File

Create a `.env` file in your project directory:

```bash
# LLM Configuration
LLM_PROVIDER="ollama"
LLM_MODEL="qwen3-coder:30b"
LLM_API_KEY="ollama"
LLM_ENDPOINT="http://localhost:11434/v1"

# Embedding Configuration
EMBEDDING_PROVIDER="ollama"
EMBEDDING_MODEL="embeddinggemma:latest"
EMBEDDING_ENDPOINT="http://localhost:11434/api/embed"
EMBEDDING_DIMENSIONS="768"

# Optional
TELEMETRY_DISABLED=true
```

## Loading Configuration

Pygrad automatically loads environment variables. For Python scripts:

```python
from dotenv import load_dotenv
load_dotenv()  # Load from .env file

import pygrad as pg
# Now pg.add(), pg.search(), etc. will use your configuration
```

## Next Steps

- [Configure Ollama](ollama.md) for local LLM usage
- [Configure OpenAI](openai.md) for cloud-based inference
- [Configure Database](database.md) for production deployments

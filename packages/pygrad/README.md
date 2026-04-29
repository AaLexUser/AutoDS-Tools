<div align="center">

# `pygrad`

[![Documentation](https://img.shields.io/badge/docs-mkdocs-white)](https://aalexuser.github.io/pygrad/)
[![License](https://img.shields.io/badge/license-BSD%203--Clause-white)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-white)](https://python.org)

**Build searchable knowledge graphs from Python repository documentation using Graph RAG.**
</div>

## Installation

```bash
pip install git+https://github.com/AaLexUser/pygrad.git
```

## Quick Start

```python
import asyncio
import pygrad as pg

async def main():
    # Add a repository to the knowledge graph
    await pg.add("https://github.com/psf/requests")

    # Search the knowledge graph
    result = await pg.search(
        "https://github.com/psf/requests",
        "How do I make a POST request with JSON data?"
    )
    print(result)

    # List all indexed repositories
    datasets = await pg.list()
    for ds in datasets:
        print(f"  - {ds.name}")

    # Visualize the knowledge graph
    await pg.visualize("./graph.html")

    # Delete a repository
    await pg.delete("https://github.com/psf/requests")

asyncio.run(main())
```

### CLI Usage

```bash
# Add a repository
pygrad add https://github.com/owner/repo

# Search the knowledge graph
pygrad ask https://github.com/owner/repo "How do I authenticate?"

# List indexed repositories
pygrad list

# Visualize the graph
pygrad visualize -o ./graph.html

# Delete a repository
pygrad delete https://github.com/owner/repo
```

### REST Server

```bash
# Install server dependencies
pip install git+https://github.com/AaLexUser/pygrad.git[server]

# Run
uvicorn pygrad.server:app --host 0.0.0.0 --port 8446
```

Or with Docker:

```bash
# Build
docker build -t pygrad-server .

# Run (pass your .env for LLM / DB config)
docker run -p 8446:8446 --env-file .env pygrad-server
```

The server exposes the same five operations as the CLI. See the [REST Server API docs](https://aalexuser.github.io/pygrad/api/server/) for endpoint details.


## How It Works

```
Repository → Parse (TreeSitter) → Extract API → Build Graph → Search (RAG)
```

1. **Clone**: Downloads the repository
2. **Parse**: Uses TreeSitter to extract code structure
3. **Extract**: Identifies classes, functions, docstrings, and examples
4. **Index**: Builds a knowledge graph (Cognee or Neo4j GraphRAG)
5. **Search**: Enables natural language queries over the codebase

### Backend Comparison

| Feature | Cognee | Neo4j GraphRAG |
|---------|--------|----------------|
| Setup | Automatic | Requires Neo4j |
| Repository Isolation | Datasets | Property-based |
| Vector Search | ✓ | ✓ |
| Graph Traversal | ✓ | ✓ (Cypher) |
| Visualization | Built-in | Neo4j Browser |

## API Reference

### Core Functions

| Function | Description |
|----------|-------------|
| `pg.add(url)` | Add a repository to the knowledge graph |
| `pg.search(url, query)` | Search with natural language |
| `pg.list()` | List all indexed datasets |
| `pg.delete(url)` | Remove a repository |
| `pg.visualize(path)` | Export graph as HTML |
| `pg.get_dataset(name)` | Get dataset by name |

## Configuration

Pygrad uses environment variables for configuration:

### Search Backend

Pygrad supports two search backends:

**Cognee (Default)**
```bash
SEARCH_BACKEND="cognee"
```

**Neo4j GraphRAG** (with repository isolation)
```bash
SEARCH_BACKEND="neo4j-graphrag"

# Neo4j connection
NEO4J_URI="bolt://localhost:7687"
NEO4J_USERNAME="neo4j"
NEO4J_PASSWORD="pleaseletmein"
NEO4J_DATABASE="neo4j"
```

#### Quick Start with Docker

Start Neo4j using the included docker-compose:

```bash
# Start Neo4j
docker-compose up -d

# Or use the helper script
./scripts/neo4j.sh start

# Check status
./scripts/neo4j.sh status

# View logs
./scripts/neo4j.sh logs

# Open Cypher shell
./scripts/neo4j.sh shell

# Test connection
./scripts/neo4j.sh test
```

Access Neo4j Browser at http://localhost:7474 (credentials: neo4j/pleaseletmein)

See [docs/neo4j-setup.md](docs/neo4j-setup.md) for detailed setup instructions.

### Ollama (Local LLM)

```bash
# LLM
LLM_PROVIDER="ollama"
LLM_MODEL="qwen3-coder:30b"
LLM_ENDPOINT="http://localhost:11434/v1"

# Embeddings
EMBEDDING_PROVIDER="ollama"
EMBEDDING_MODEL="embeddinggemma:latest"
EMBEDDING_ENDPOINT="http://localhost:11434/api/embed"
EMBEDDING_DIMENSIONS="768"
```

### OpenAI

```bash
LLM_PROVIDER="openai"
LLM_API_KEY="sk-..."
LLM_MODEL="gpt-4o"

EMBEDDING_PROVIDER="openai"
EMBEDDING_MODEL="text-embedding-3-small"
```

### Database Options

**Cognee Backend** (PostgreSQL + pgvector for production)
```bash
VECTOR_DB_PROVIDER="pgvector"
DB_PROVIDER="postgres"
DB_HOST="localhost"
DB_PORT="5432"
DB_NAME="cognee_db"
DB_USERNAME="cognee"
DB_PASSWORD="cognee"

GRAPH_DATABASE_PROVIDER="neo4j"
GRAPH_DATABASE_URL="bolt://localhost:7687"
```

**Neo4j GraphRAG Backend**
```bash
SEARCH_BACKEND="neo4j-graphrag"
NEO4J_URI="bolt://localhost:7687"
NEO4J_USERNAME="neo4j"
NEO4J_PASSWORD="your-secure-password"
NEO4J_DATABASE="neo4j"
```

See the [Configuration Guide](https://aalexuser.github.io/pygrad/configuration/) for more options.

## Development

```bash
# From the monorepo root
cd packages/pygrad

# Install
pip install -e ".[dev]"

# Test
just test

# Docs
pip install -e ".[docs]"
mkdocs serve
```

## Documentation

Full documentation is available at [aalexuser.github.io/pygrad](https://aalexuser.github.io/pygrad/).

- [Getting Started](https://aalexuser.github.io/pygrad/getting-started/)
- [Examples](https://aalexuser.github.io/pygrad/examples/)
- [Architecture](https://aalexuser.github.io/pygrad/architecture/)
- [API Reference](https://aalexuser.github.io/pygrad/api/)

## License

BSD 3-Clause License

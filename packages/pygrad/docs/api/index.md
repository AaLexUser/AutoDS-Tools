# API Reference

Complete API documentation for pygrad.

## Module Overview

pygrad provides a numpy-style API for building knowledge graphs from Python repositories.

```python
import pygrad as pg

# Core functions
await pg.add("https://github.com/owner/repo")
result = await pg.search("https://github.com/owner/repo", "How to use X?")
datasets = await pg.list()
await pg.delete("https://github.com/owner/repo")
await pg.visualize("./graph.html")
```

## API Modules

| Module | Description |
|--------|-------------|
| [Core](core.md) | Main API functions (`add`, `search`, `list`, `delete`, `visualize`) |
| [Repository](repository.md) | Repository cloning and identification utilities |
| [Processor](processor.md) | Python code processing and XML generation |
| [Parser](parser.md) | TreeSitter-based Python parsing |

## Quick Reference

### Core Functions

| Function | Description |
|----------|-------------|
| `pg.add(url)` | Add a repository to the knowledge graph |
| `pg.search(url, query)` | Search a repository's knowledge graph |
| `pg.list()` | List all indexed datasets |
| `pg.delete(url)` | Delete a repository from the knowledge graph |
| `pg.visualize(path)` | Export the knowledge graph as HTML |
| `pg.get_dataset(name)` | Get a dataset by name |

### Low-Level APIs

| Class/Function | Module | Description |
|----------------|--------|-------------|
| `RepoTreeSitter` | `parser` | Parse Python files with TreeSitter |
| `PythonRepositoryProcessor` | `processor` | Process repositories into XML |
| `process_repository()` | `processor` | High-level repository processing |
| `clone_repository()` | `repository` | Clone a Git repository |
| `get_repository_id()` | `repository` | Extract repository identifier from URL |

## Type Hints

All functions are fully typed. Enable type checking in your IDE for the best experience:

```python
from pygrad import add, search, list, delete, visualize
from pygrad import ClassInfo, FunctionInfo  # Data classes
from pygrad import RepoTreeSitter  # Parser
from pygrad import PythonRepositoryProcessor  # Processor
```

## Async/Await

All core functions are async and must be awaited:

```python
import asyncio
import pygrad as pg

async def main():
    await pg.add("https://github.com/owner/repo")
    result = await pg.search("https://github.com/owner/repo", "query")
    print(result)

asyncio.run(main())
```

## Configuration

pygrad uses environment variables for configuration. See the [Configuration Guide](../configuration/index.md) for details.

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | LLM provider (`ollama`, `openai`) | `ollama` |
| `LLM_MODEL` | Model name | `qwen3-coder:30b` |
| `EMBEDDING_PROVIDER` | Embedding provider | `ollama` |
| `EMBEDDING_MODEL` | Embedding model | `embeddinggemma:latest` |

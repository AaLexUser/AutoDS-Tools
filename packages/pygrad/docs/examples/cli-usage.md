# CLI Usage

Pygrad provides a command-line interface for common operations.

## Available Commands

| Command | Description |
|---------|-------------|
| `pygrad add <url>` | Index a repository |
| `pygrad ask <url> <query>` | Search indexed documentation |
| `pygrad list` | List indexed repositories |
| `pygrad delete <url>` | Remove a repository |
| `pygrad visualize` | Export knowledge graph as HTML |

## Adding Repositories

Index a GitHub repository:

```bash
# Basic usage
pygrad add https://github.com/pydantic/pydantic

# Multiple repositories
pygrad add https://github.com/fastapi/fastapi
pygrad add https://github.com/encode/httpx
pygrad add https://github.com/pallets/flask
```

## Searching Documentation

Query indexed repositories:

```bash
# Basic search
pygrad ask https://github.com/pydantic/pydantic "How to validate emails?"

# Quoted queries for complex questions
pygrad ask https://github.com/fastapi/fastapi "What's the difference between Query and Path?"

# API-specific queries
pygrad ask https://github.com/encode/httpx "Show me examples of setting headers"
```

## Listing Repositories

View all indexed repositories:

```bash
pygrad list
```

Output:
```
pydantic-pydantic
fastapi-fastapi
encode-httpx
```

## Deleting Repositories

Remove a repository from the knowledge graph:

```bash
pygrad delete https://github.com/pydantic/pydantic
```

## Visualizing the Knowledge Graph

Export an interactive HTML visualization:

```bash
# Default output (./pygrad.html)
pygrad visualize

# Custom output path
pygrad visualize -o ./my_graph.html
pygrad visualize --output /path/to/graph.html
```

## Environment Variables

Configure Pygrad behavior with environment variables:

```bash
# Set LLM configuration
export LLM_PROVIDER="ollama"
export LLM_MODEL="qwen3-coder:30b"
export LLM_ENDPOINT="http://localhost:11434/v1"

# Then run commands
pygrad add https://github.com/owner/repo
```

Or use a `.env` file:

```bash
# Load from .env file (requires python-dotenv)
source .env && pygrad add https://github.com/owner/repo
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (clone failed, search failed, etc.) |

## Tips and Tricks

### Check if a Repository is Indexed

```bash
# Use list and grep
pygrad list | grep -q "pydantic-pydantic" && echo "Indexed" || echo "Not indexed"
```

### Pipe Output to Other Tools

```bash
# Format with markdown viewer
pygrad ask https://github.com/pydantic/pydantic "Quick start guide" | glow -
```

## Next Steps

- [Integration patterns](integration.md)
- [Architecture overview](../architecture/index.md)
- [Configuration guide](../configuration/index.md)

# OpenAI Configuration

Use OpenAI's GPT models for high-quality documentation search.

## Prerequisites

1. OpenAI API account
2. API key from [platform.openai.com](https://platform.openai.com/api-keys)

## Configuration

Create a `.env` file:

```bash
# LLM Configuration
LLM_PROVIDER="openai"
LLM_MODEL="gpt-4o"
LLM_API_KEY="sk-your-api-key-here"

# Embedding Configuration
EMBEDDING_PROVIDER="openai"
EMBEDDING_MODEL="text-embedding-3-small"
```

## Full Configuration

```bash
# LLM Configuration
LLM_PROVIDER="openai"
LLM_MODEL="gpt-4o"
LLM_API_KEY="sk-your-api-key-here"

# Embedding Configuration
EMBEDDING_PROVIDER="openai"
EMBEDDING_MODEL="text-embedding-3-small"
EMBEDDING_DIMENSIONS="1536"

# Optional: Use Azure OpenAI
# LLM_ENDPOINT="https://your-resource.openai.azure.com/"
# AZURE_OPENAI_API_KEY="your-azure-key"
```

## Verify Setup

```python
import asyncio
import pygrad as pg


async def test_openai():
    print("Testing OpenAI configuration...")
    
    # Index a repository
    await pg.add("https://github.com/encode/httpx")
    print("Repository indexed!")
    
    # Search
    result = await pg.search(
        "https://github.com/encode/httpx",
        "How to make HTTP requests?"
    )
    print(result)


asyncio.run(test_openai())
```

## Cost Optimization

### Use Smaller Models

For development and testing:

```bash
LLM_MODEL="gpt-3.5-turbo"
EMBEDDING_MODEL="text-embedding-3-small"
```

### Batch Processing

Index repositories in batches to reduce API calls:

```python
# Pygrad handles batching internally
await pg.add("https://github.com/owner/repo")
```

### Cache Results

Pygrad caches indexed repositories, so subsequent searches don't require re-indexing.

## Azure OpenAI

For Azure OpenAI deployments:

```bash
LLM_PROVIDER="azure"
LLM_ENDPOINT="https://your-resource.openai.azure.com/"
LLM_MODEL="your-deployment-name"
AZURE_OPENAI_API_KEY="your-azure-key"
AZURE_OPENAI_API_VERSION="2024-02-01"

EMBEDDING_PROVIDER="azure"
EMBEDDING_MODEL="your-embedding-deployment-name"
```

## Troubleshooting

### Authentication Error

```
AuthenticationError: Incorrect API key provided
```

Verify your API key:

```bash
# Test with curl
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer sk-your-key"
```

### Rate Limits

If you hit rate limits:

1. Use a smaller model
2. Add delays between requests
3. Upgrade your OpenAI plan

### Timeout Errors

For large repositories, increase timeout:

```python
# Handle timeouts gracefully
import asyncio

try:
    await asyncio.wait_for(pg.add(url), timeout=300)
except asyncio.TimeoutError:
    print("Processing took too long, try a smaller repository")
```

## Next Steps

- [Configure database backends](database.md)
- [Use Ollama for local processing](ollama.md)
- [Explore examples](../examples/index.md)

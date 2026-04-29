# Ollama Configuration

Use Ollama for local LLM inference with complete privacy.

## Why Ollama?

- **Privacy**: All processing happens locally
- **No API costs**: Free to use after setup
- **Offline**: Works without internet connection
- **Fast**: Local inference can be faster for repeated queries

## Installation

=== "macOS"

    ```bash
    brew install ollama
    ```

=== "Linux"

    ```bash
    curl -fsSL https://ollama.com/install.sh | sh
    ```

=== "Windows"

    Download from [ollama.com/download/windows](https://ollama.com/download/windows)

## Start Ollama Server

```bash
ollama serve
```

The server runs on `http://localhost:11434` by default.

## Pull Required Models

### LLM Model

We recommend `qwen3-coder` for code-related documentation:

```bash
# Large model (30B) - Best quality
ollama pull qwen3-coder:30b

# Medium model (8B) - Good balance
ollama pull qwen3-coder:8b

# Small model (1.5B) - Fastest
ollama pull qwen3-coder:1.5b
```

Alternative models:

```bash
ollama pull llama3.2:latest
ollama pull mistral:latest
ollama pull codellama:latest
```

### Embedding Model

```bash
# Recommended
ollama pull embeddinggemma:latest

# Alternatives
ollama pull nomic-embed-text:latest
ollama pull mxbai-embed-large:latest
```

## Configuration

Create a `.env` file:

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

# Tokenizer for text chunking
HUGGINGFACE_TOKENIZER="Qwen/Qwen3-Coder-30B-A3B-Instruct"

# Disable telemetry (optional)
TELEMETRY_DISABLED=true
```

## Verify Setup

Test that everything is working:

```python
import asyncio
import pygrad as pg


async def test_ollama():
    # This should work if Ollama is configured correctly
    print("Testing Ollama configuration...")
    
    # Index a small repository
    await pg.add("https://github.com/encode/httpx")
    print("Repository indexed successfully!")
    
    # Test search
    result = await pg.search(
        "https://github.com/encode/httpx",
        "How to make a GET request?"
    )
    print(f"Search result: {result[:200]}...")


asyncio.run(test_ollama())
```

## Troubleshooting

### Connection Refused

If you see "Connection refused" errors:

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# If not, start it
ollama serve
```

### Model Not Found

If a model is not found:

```bash
# List installed models
ollama list

# Pull the missing model
ollama pull qwen3-coder:30b
```

### Out of Memory

For large models on limited hardware:

```bash
# Use a smaller model
ollama pull qwen3-coder:8b
# Or
ollama pull qwen3-coder:1.5b
```

Update your `.env`:

```bash
LLM_MODEL="qwen3-coder:8b"
```

### Slow Performance

For faster inference:

1. Use a smaller model
2. Ensure you have GPU acceleration
3. Increase Ollama's memory limit

```bash
# Set memory limit (in GB)
export OLLAMA_MAX_LOADED_MODELS=1
export OLLAMA_NUM_PARALLEL=1
```

## Advanced Configuration

### Custom Ollama Host

If Ollama runs on a different machine:

```bash
LLM_ENDPOINT="http://192.168.1.100:11434/v1"
EMBEDDING_ENDPOINT="http://192.168.1.100:11434/api/embed"
```

### GPU Configuration

Ollama automatically uses GPU if available. To verify:

```bash
ollama run qwen3-coder:30b
# Check GPU usage in output
```

### Memory Management

For systems with limited RAM:

```bash
# Limit loaded models
export OLLAMA_MAX_LOADED_MODELS=1

# Set context window
export OLLAMA_NUM_CTX=4096
```

## Recommended Models

| Use Case | Model | Size | Quality |
|----------|-------|------|---------|
| Development | `qwen3-coder:8b` | ~5GB | Good |
| Production | `qwen3-coder:30b` | ~18GB | Best |
| Low memory | `qwen3-coder:1.5b` | ~1GB | Basic |
| General | `llama3.2:latest` | ~4GB | Good |

## Next Steps

- [Configure database backends](database.md)
- [Learn about the architecture](../architecture/index.md)
- [Explore examples](../examples/index.md)

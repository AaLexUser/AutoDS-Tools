# Installation

This guide covers how to install Pygrad on your system.

## Requirements

- **Python**: 3.10 or higher
- **Git**: Required for cloning repositories
- **LLM Provider**: Ollama (recommended) or OpenAI API key

## Install from PyPI

The simplest way to install Pygrad is using pip:

```bash
pip install git+https://github.com/AaLexUser/pygrad.git
```

## Install from Source

To install the latest development version:

```bash
git clone https://github.com/AaLexUser/AutoDS-Tools
cd AutoDS-Tools/packages/pygrad
pip install -e ".[dev]"
```

## Verify Installation

Check that Pygrad is installed correctly:

```bash
python -c "import pygrad; print(pygrad.__version__)"
```

You should see the version number printed.

## Install Ollama (Recommended)

Pygrad works best with a local LLM. We recommend Ollama:

=== "macOS"

    ```bash
    brew install ollama
    ollama serve
    ```

=== "Linux"

    ```bash
    curl -fsSL https://ollama.com/install.sh | sh
    ollama serve
    ```

=== "Windows"

    Download from [ollama.com](https://ollama.com/download/windows)

Then pull the required models:

```bash
# LLM model
ollama pull qwen3-coder:30b

# Embedding model
ollama pull embeddinggemma:latest
```

## Environment Setup

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

## Troubleshooting

### Import Error

If you get an import error, make sure you have all dependencies installed:

```bash
pip install cognee tree-sitter tree-sitter-python
```

### Ollama Connection Error

Make sure Ollama is running:

```bash
ollama serve
```

### Permission Error on Clone

If you can't clone private repositories, set up SSH keys or use HTTPS with authentication.

## Next Steps

Now that you have Pygrad installed, continue to the [Quick Start guide](quickstart.md).

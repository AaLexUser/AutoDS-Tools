# Quick Start

Get started with Pygrad in 5 minutes!

## Your First Knowledge Graph

Let's index a popular Python library and ask questions about it.

### Step 1: Import Pygrad

```python
import pygrad as pg
```

### Step 2: Index a Repository

```python
# Index the Pydantic library
await pg.add("https://github.com/pydantic/pydantic")
```

!!! note "First run takes time"
    The first time you index a repository, Pygrad will:
    
    1. Clone the repository
    2. Parse all Python files
    3. Extract usage examples
    4. Build the knowledge graph
    
    This may take a few hours depending on the repository size.

### Step 3: Ask Questions

```python
# Ask about the library
result = await pg.search(
    "https://github.com/pydantic/pydantic",
    "How do I validate email addresses?"
)
print(result)
```

### Step 4: List Indexed Repositories

```python
# See all indexed repositories
datasets = await pg.list()
for ds in datasets:
    print(f"- {ds.name}")
```

### Step 5: Clean Up (Optional)

```python
# Remove a repository from the knowledge graph
await pg.delete("https://github.com/pydantic/pydantic")
```

## Complete Example

Here's a complete script you can run:

```python
import asyncio
import pygrad as pg


async def main():
    # Index a repository
    print("Indexing repository...")
    await pg.add("https://github.com/encode/httpx")
    print("Done!")

    # Ask questions
    questions = [
        "How do I make a GET request?",
        "How do I set custom headers?",
        "How do I handle timeouts?",
    ]

    for question in questions:
        print(f"\n> {question}")
        result = await pg.search(
            "https://github.com/encode/httpx",
            question
        )
        print(result)

    # List all indexed repos
    print("\n--- Indexed Repositories ---")
    datasets = await pg.list()
    for ds in datasets:
        print(f"- {ds.name}")


if __name__ == "__main__":
    asyncio.run(main())
```

## Using the CLI

You can also use Pygrad from the command line:

```bash
# Index a repository
pygrad add https://github.com/encode/httpx

# Ask a question
pygrad ask https://github.com/encode/httpx "How to make POST request?"

# List indexed repositories
pygrad list

# Visualize the knowledge graph
pygrad visualize -o graph.html

# Delete a repository
pygrad delete https://github.com/encode/httpx
```

## What's Next?

- [Explore more examples](../examples/index.md)
- [Learn about the architecture](../architecture/index.md)
- [Configure your LLM provider](../configuration/index.md)
- [Read the API reference](../api/index.md)

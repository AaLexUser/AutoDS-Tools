# Basic Usage

This guide covers the fundamental operations in Pygrad.

## Importing Pygrad

Always import Pygrad using the numpy-style convention:

```python
import pygrad as pg
```

## Adding a Repository

Index a GitHub repository to make it searchable:

```python
import pygrad as pg

# Add a public repository
await pg.add("https://github.com/pydantic/pydantic")
```

### What Happens During `pg.add()`

1. **Clone**: The repository is cloned (shallow clone for speed)
2. **Parse**: All Python files are analyzed using Tree-sitter
3. **Extract**: Classes, functions, methods, and docstrings are extracted
4. **Examples**: Usage examples are mined from tests and example files
5. **Generate**: Structured API documentation is created in XML format
6. **Index**: The documentation is ingested into the Cognee knowledge graph

### Progress Tracking

For large repositories, you may want to track progress:

```python
import pygrad as pg

print("Starting indexing...")
await pg.add("https://github.com/scikit-learn/scikit-learn")
print("Indexing complete!")
```

## Searching the Knowledge Graph

Once indexed, you can ask questions about the library:

```python
import pygrad as pg

url = "https://github.com/pydantic/pydantic"

# Ask a question
result = await pg.search(url, "How do I validate email addresses?")
print(result)
```

### Search Tips

- Be specific in your questions
- Ask about specific APIs, classes, or methods
- Include context about what you're trying to accomplish

```python
# Good queries
result = await pg.search(url, "How to create a custom validator?")
result = await pg.search(url, "What exceptions does BaseModel raise?")
result = await pg.search(url, "Show examples of Field with default values")

# Less effective queries
result = await pg.search(url, "help")  # Too vague
result = await pg.search(url, "error") # Not specific enough
```

## Listing Indexed Repositories

View all repositories in your knowledge graph:

```python
import pygrad as pg

datasets = await pg.list()

if datasets:
    print("Indexed repositories:")
    for ds in datasets:
        print(f"  - {ds.name}")
else:
    print("No repositories indexed yet.")
```

## Checking if a Repository is Indexed

```python
import pygrad as pg

url = "https://github.com/pydantic/pydantic"
dataset = await pg.get_dataset("pydantic-pydantic")

if dataset:
    print("Pydantic is indexed!")
else:
    print("Pydantic is not indexed yet.")
    await pg.add(url)
```

## Deleting a Repository

Remove a repository from the knowledge graph:

```python
import pygrad as pg

url = "https://github.com/pydantic/pydantic"
await pg.delete(url)
print("Repository removed from knowledge graph.")
```

## Visualizing the Knowledge Graph

Export an interactive HTML visualization:

```python
import pygrad as pg

# Create visualization
path = await pg.visualize("./my_graph.html")
print(f"Graph saved to: {path}")
```

Open the HTML file in a browser to explore the knowledge graph interactively.

## Complete Example

Here's a complete workflow:

```python
import asyncio
import pygrad as pg


async def main():
    url = "https://github.com/encode/httpx"
    
    # Check if already indexed
    dataset = await pg.get_dataset("encode-httpx")
    
    if not dataset:
        print("Indexing httpx...")
        await pg.add(url)
        print("Done!")
    
    # Ask questions
    questions = [
        "How do I make a GET request?",
        "How do I set request headers?",
        "How do I handle timeouts?",
        "What is the difference between Client and AsyncClient?",
    ]
    
    for q in questions:
        print(f"\n{'='*60}")
        print(f"Q: {q}")
        print("-" * 60)
        result = await pg.search(url, q)
        print(result)
    
    # Show all indexed repos
    print(f"\n{'='*60}")
    print("All indexed repositories:")
    for ds in await pg.list():
        print(f"  - {ds.name}")


if __name__ == "__main__":
    asyncio.run(main())
```

## Error Handling

Handle common errors gracefully:

```python
import pygrad as pg


async def safe_add(url: str) -> bool:
    """Safely add a repository with error handling."""
    try:
        await pg.add(url)
        return True
    except RuntimeError as e:
        if "clone" in str(e).lower():
            print(f"Failed to clone repository: {url}")
        else:
            print(f"Error processing repository: {e}")
        return False


async def safe_search(url: str, query: str) -> str:
    """Safely search with fallback message."""
    try:
        result = await pg.search(url, query)
        if result == "The library is not yet indexed.":
            print(f"Repository not indexed. Adding it now...")
            await pg.add(url)
            result = await pg.search(url, query)
        return result
    except Exception as e:
        return f"Search failed: {e}"
```

## Next Steps

- [Explore search query patterns](searching.md)
- [Use the CLI](cli-usage.md)

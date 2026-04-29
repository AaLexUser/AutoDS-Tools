# Core API

The core module provides the main API functions for building and querying knowledge graphs.

## Usage

```python
import pygrad as pg

# Add a repository
await pg.add("https://github.com/owner/repo")

# Search the knowledge graph
result = await pg.search("https://github.com/owner/repo", "How do I authenticate?")

# List all datasets
datasets = await pg.list()

# Delete a repository
await pg.delete("https://github.com/owner/repo")

# Visualize the graph
await pg.visualize("./knowledge-graph.html")
```

---

## Functions

### add

```python
async def add(url: str) -> None
```

Add a repository to the knowledge graph.

This function:

1. Clones the repository (if not already cached)
2. Parses all Python files using TreeSitter
3. Extracts classes, functions, methods, and docstrings
4. Generates XML API documentation
5. Indexes the documentation into the knowledge graph

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `url` | `str` | GitHub repository URL (e.g., `https://github.com/owner/repo`) |

**Returns:** `None`

**Raises:**

- `ValueError`: If the URL is invalid
- `subprocess.CalledProcessError`: If git clone fails

**Example:**

```python
import pygrad as pg

# Add a single repository
await pg.add("https://github.com/psf/requests")

# Add multiple repositories
repos = [
    "https://github.com/psf/requests",
    "https://github.com/pallets/flask",
    "https://github.com/django/django",
]
for repo in repos:
    await pg.add(repo)
    print(f"Added: {repo}")
```

---

### search

```python
async def search(url: str, query: str) -> str
```

Query a repository's knowledge graph using natural language.

Uses Graph RAG (Retrieval Augmented Generation) to search the knowledge graph
and generate contextual answers.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `url` | `str` | GitHub repository URL |
| `query` | `str` | Natural language query |

**Returns:** `str` - The search result as a string

**Example:**

```python
import pygrad as pg

# Search for usage patterns
result = await pg.search(
    "https://github.com/psf/requests",
    "How do I make a POST request with JSON data?"
)
print(result)

# Search for API information
result = await pg.search(
    "https://github.com/pallets/flask",
    "What decorators are available for routes?"
)
print(result)
```

**Query Tips:**

- Be specific: "How do I authenticate with OAuth2?" vs "authentication"
- Ask about patterns: "What's the recommended way to handle errors?"
- Reference concepts: "How does the session management work?"

---

### list

```python
async def list() -> list[Any]
```

List all indexed datasets (repositories).

**Returns:** `list[Any]` - List of dataset objects with `name` and `id` attributes

**Example:**

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

---

### delete

```python
async def delete(url: str) -> None
```

Delete a repository from the knowledge graph.

This removes the indexed data but does not delete the cached repository files.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `url` | `str` | GitHub repository URL |

**Returns:** `None`

**Example:**

```python
import pygrad as pg

# Delete a single repository
await pg.delete("https://github.com/owner/repo")

# Delete all repositories
datasets = await pg.list()
for ds in datasets:
    # Reconstruct URL from dataset name
    await pg.delete(f"https://github.com/{ds.name.replace('_', '/')}")
```

---

### visualize

```python
async def visualize(path: str = "./pygrad.html") -> str
```

Export the knowledge graph as an interactive HTML visualization.

**Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `path` | `str` | `"./pygrad.html"` | Output file path |

**Returns:** `str` - Path to the generated HTML file

**Example:**

```python
import pygrad as pg

# Generate default visualization
await pg.visualize()

# Generate to custom path
path = await pg.visualize("./docs/knowledge-graph.html")
print(f"Visualization saved to: {path}")
```

---

### get_dataset

```python
async def get_dataset(dataset_name: str, default: Any = None) -> Any
```

Get a dataset by name.

**Parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `dataset_name` | `str` | - | Name of the dataset (repository ID) |
| `default` | `Any` | `None` | Default value if not found |

**Returns:** Dataset object or `default` if not found

**Example:**

```python
import pygrad as pg
from pygrad import get_repository_id

url = "https://github.com/owner/repo"
repo_id = get_repository_id(url)

dataset = await pg.get_dataset(repo_id)
if dataset:
    print(f"Found dataset: {dataset.name}")
else:
    print("Dataset not found, indexing...")
    await pg.add(url)
```

---

## Internal Functions

These functions are used internally but are available for advanced use cases.

### _create_xml_api_doc

```python
async def _create_xml_api_doc(url: str) -> Path
```

Create XML API documentation for a repository.

### _split_xml_api

```python
def _split_xml_api(xml_api_path: Path) -> list[str]
```

Split XML API into documents for indexing.

### _cognee_add_xml_api

```python
async def _cognee_add_xml_api(xml_api_path: Path, dataset_name: str) -> None
```

Add XML API to Cognee knowledge graph.

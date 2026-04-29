# Examples

Explore practical examples of using Pygrad for various use cases.

## Available Examples

<div class="grid" markdown>

<div class="card" markdown>

### [:material-play: Basic Usage](basic-usage.md)

Core operations: adding repositories, searching, and managing datasets.

</div>

<div class="card" markdown>

### [:material-magnify: Search Queries](searching.md)

Various search query patterns and techniques for getting the best results.

</div>

<div class="card" markdown>

### [:material-console: CLI Usage](cli-usage.md)

Command-line interface examples and workflows.

</div>

<div class="card" markdown>

### [:material-puzzle: Integration](integration.md)

Integrating Pygrad with FastAPI, Jupyter, and batch processing.

</div>

</div>

## Quick Reference

| Function | Description | Example |
|----------|-------------|---------|
| `pg.add(url)` | Index a repository | `await pg.add("https://github.com/owner/repo")` |
| `pg.search(url, query)` | Search documentation | `await pg.search(url, "How to use X?")` |
| `pg.list()` | List indexed repos | `datasets = await pg.list()` |
| `pg.delete(url)` | Remove a repository | `await pg.delete(url)` |
| `pg.visualize(path)` | Export graph as HTML | `await pg.visualize("graph.html")` |

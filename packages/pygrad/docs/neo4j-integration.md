# Neo4j Integration

This document describes the Neo4j graph database integration for Pygrad, which allows converting Python repository API documentation into a queryable knowledge graph.

## Overview

The Neo4j integration provides an alternative to the XML-based output format. Instead of generating hierarchical XML documents, the repository data is stored as a graph database with nodes representing entities (classes, functions, methods, examples) and edges representing their relationships.

## Architecture

### Node Types

#### Class Nodes

Represent Python classes extracted from the repository.

**Label:** `Class`

**Properties:**
- `name`: Class name (e.g., "PythonRepositoryProcessor")
- `api_path`: Fully qualified API path (e.g., "pygrad.processor.processor.PythonRepositoryProcessor")
- `description`: Class docstring/description
- `init_parameters`: Initialization parameters as string
- `init_description`: Description of initialization method

#### Function Nodes

Represent standalone functions (not class methods).

**Label:** `Function`

**Properties:**
- `name`: Function name
- `api_path`: Fully qualified API path
- `description`: Function docstring/description
- `header`: Function signature (e.g., "def process_repository(path, output_file)")
- `output`: Return type annotation if available

#### Method Nodes

Represent class methods.

**Label:** `Method`

**Properties:**
- `name`: Method name
- `api_path`: Fully qualified API path including class
- `description`: Method docstring/description
- `header`: Method signature
- `output`: Return type annotation if available

#### Example Nodes

Represent usage examples extracted from the repository (tests, documentation, examples).

**Label:** `Example`

**Properties:**
- `id`: Unique identifier (generated from source_file:line:code_hash)
- `source_file`: File path where example was found
- `example_type`: Type of example (e.g., "function_call", "class_instantiation", "method_call")
- `line`: Line number in source file
- `variable`: Variable name if applicable
- `header`: Function/method header if applicable
- `source_code`: The actual example code

**Deduplication:** Examples are deduplicated based on their unique ID. If the same example is used by multiple entities, they all reference the same Example node.

### Relationships

#### CONTAINS

Links classes to their methods.

```
(:Class)-[:CONTAINS]->(:Method)
```

#### HAS_EXAMPLE

Links classes, functions, and methods to usage examples.

```
(:Class)-[:HAS_EXAMPLE]->(:Example)
(:Function)-[:HAS_EXAMPLE]->(:Example)
(:Method)-[:HAS_EXAMPLE]->(:Example)
```

## Implementation

### Core Components

#### `Neo4jGraphConverter`

Located in `src/pygrad/processor/neo4j_graph.py`.

Main class responsible for:
- Managing Neo4j database connection
- Creating nodes with proper constraints
- Handling example deduplication
- Creating relationships between entities

**Key Methods:**

- `save_repository_graph()`: Main entry point for saving graph data
- `_create_class_node()`: Creates Class nodes
- `_create_function_node()`: Creates Function nodes
- `_create_method_node()`: Creates Method nodes and CONTAINS relationships
- `_create_example_node()`: Creates or merges Example nodes (with deduplication)
- `_create_example_relationship()`: Creates HAS_EXAMPLE relationships

#### `PythonRepositoryProcessor.save_repository_to_neo4j()`

Located in `src/pygrad/processor/processor.py`.

High-level method that wraps the Neo4j converter, providing a simple interface for saving repository data.

#### `process_repository_to_neo4j()`

Located in `src/pygrad/processor/processor.py`.

Convenience function that:
1. Processes repository using tree-sitter
2. Extracts usage examples
3. Saves everything to Neo4j in one call

### Example Deduplication Strategy

Examples are identified using a composite key:

```python
example_id = f"{source_file}:{line}:{md5_hash_of_code[:8]}"
```

The Neo4j `MERGE` operation ensures that examples with the same ID are not duplicated. When multiple entities reference the same example, they all create relationships to the same Example node.

## Usage

### Basic Usage

```python
import asyncio
from pygrad.processor.processor import process_repository_to_neo4j

async def main():
    stats = await process_repository_to_neo4j(
        repository_path="/path/to/repo",
        neo4j_uri="bolt://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="password",
        database="neo4j",
        clear_existing=True
    )
    print(f"Created {stats['classes']} classes")
    print(f"Created {stats['functions']} functions")
    print(f"Created {stats['methods']} methods")
    print(f"Created {stats['examples']} examples")
    print(f"Created {stats['relationships']} relationships")

asyncio.run(main())
```

### Advanced Usage

```python
from pygrad.processor.processor import PythonRepositoryProcessor
from pygrad.processor.example_extractor import extract_examples_from_repository

# Process repository data
processor = PythonRepositoryProcessor("/path/to/repo")
classes, functions = processor.process_repository_data()

# Extract examples
api_usage_groups = extract_examples_from_repository(
    "/path/to/repo", processor.analysis_results
)
processor._merge_examples_into_data(classes, functions, api_usage_groups)

# Save to Neo4j with custom settings
stats = processor.save_repository_to_neo4j(
    classes, functions,
    neo4j_uri="bolt://localhost:7687",
    neo4j_username="neo4j",
    neo4j_password="password",
    database="my_custom_db",
    clear_existing=False  # Append to existing data
)
```

## Querying the Graph

### Common Cypher Queries

**Get all classes:**
```cypher
MATCH (c:Class)
RETURN c.name, c.api_path
```

**Find classes with their methods:**
```cypher
MATCH (c:Class)-[:CONTAINS]->(m:Method)
RETURN c.name, collect(m.name) as methods
```

**Find examples for a specific class:**
```cypher
MATCH (c:Class {name: 'PythonRepositoryProcessor'})-[:HAS_EXAMPLE]->(e:Example)
RETURN e.source_file, e.line, e.source_code
```

**Find shared examples (used by multiple entities):**
```cypher
MATCH (e:Example)<-[:HAS_EXAMPLE]-(n)
WITH e, collect(n.name) as entities
WHERE size(entities) > 1
RETURN e.source_file, e.line, entities, e.source_code
```

**Get complete class structure:**
```cypher
MATCH (c:Class {name: 'PythonRepositoryProcessor'})
OPTIONAL MATCH (c)-[:CONTAINS]->(m:Method)
OPTIONAL MATCH (c)-[:HAS_EXAMPLE]->(ce:Example)
OPTIONAL MATCH (m)-[:HAS_EXAMPLE]->(me:Example)
RETURN c, m, ce, me
```

**Find all functions with examples:**
```cypher
MATCH (f:Function)-[:HAS_EXAMPLE]->(e:Example)
RETURN f.name, count(e) as example_count
ORDER BY example_count DESC
```

**Search by description:**
```cypher
MATCH (n)
WHERE n.description CONTAINS 'repository'
RETURN labels(n)[0] as type, n.name, n.description
```

## Configuration

### Environment Variables

```bash
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USERNAME="neo4j"
export NEO4J_PASSWORD="password"
export NEO4J_DATABASE="neo4j"
```

### Neo4j Setup

**Using Docker:**
```bash
docker run -d \
  --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:latest
```

**Using Neo4j Desktop:**
1. Download from https://neo4j.com/download/
2. Create a new database
3. Start the database
4. Note the connection URI and credentials

## Comparison with XML Format

| Aspect | XML Format | Neo4j Format |
|--------|-----------|--------------|
| Structure | Hierarchical | Graph |
| Querying | XPath, text search | Cypher queries |
| Relationships | Implicit (nesting) | Explicit (edges) |
| Deduplication | Duplicates exist | Automatic |
| Scalability | File-based | Database-backed |
| Visualization | External tools needed | Built-in Neo4j Browser |
| Integration | Text processing | Graph algorithms |

## Benefits

1. **Explicit Relationships:** Class-method and entity-example relationships are first-class citizens
2. **Deduplication:** Examples shared across multiple entities are stored once
3. **Powerful Queries:** Cypher enables complex graph traversals and pattern matching
4. **Visualization:** Neo4j Browser provides interactive graph visualization
5. **Scalability:** Database-backed storage scales better than XML files
6. **Graph Algorithms:** Can leverage Neo4j's graph algorithms for analysis

## Testing

Tests are located in `tests/test_neo4j_graph.py` and use mocking to avoid requiring a live database.

Run tests:
```bash
pytest tests/test_neo4j_graph.py -v
```

## See Also

- [Neo4j Python Driver Documentation](https://neo4j.com/docs/python-manual/current/)
- [Cypher Query Language](https://neo4j.com/docs/cypher-manual/current/)
- [Example Usage](examples/index.md)

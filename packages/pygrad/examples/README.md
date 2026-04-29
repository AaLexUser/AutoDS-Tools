# Pygrad Examples

This directory contains examples demonstrating how to use Pygrad to convert Python repository data into Neo4j knowledge graphs.

## Neo4j Graph Example

### Prerequisites

1. **Neo4j Database**: You need a running Neo4j instance. You can:
   - Use [Neo4j Desktop](https://neo4j.com/download/)
   - Run Neo4j in Docker:
     ```bash
     docker run -d \
       --name neo4j \
       -p 7474:7474 -p 7687:7687 \
       -e NEO4J_AUTH=neo4j/password \
       neo4j:latest
     ```
   - Use [Neo4j Aura](https://neo4j.com/cloud/aura/) (cloud-based)

2. **Python Dependencies**: Install pygrad with Neo4j support:
   ```bash
   pip install -e .
   ```

### Configuration

Set your Neo4j connection parameters using environment variables:

```bash
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USERNAME="neo4j"
export NEO4J_PASSWORD="password"
export NEO4J_DATABASE="neo4j"
```

Or create a `.env` file in the project root with these values.

### Running the Example

```bash
python examples/neo4j_example.py
```

This will:
1. Process the current repository (pygrad itself)
2. Extract classes, functions, methods, and usage examples
3. Create a knowledge graph in Neo4j with proper relationships
4. Display statistics about the created graph

### Graph Structure

The created graph contains:

**Node Types:**
- `Class`: Python classes with properties (name, api_path, description, initialization info)
- `Function`: Standalone functions with properties (name, api_path, description, header)
- `Method`: Class methods with properties (name, api_path, description, header)
- `Example`: Usage examples with properties (source_file, line, source_code, type)

**Relationships:**
- `(:Class)-[:CONTAINS]->(:Method)`: Classes contain methods
- `(:Class|Function|Method)-[:HAS_EXAMPLE]->(:Example)`: Entities have usage examples

**Example Deduplication:**
Examples are deduplicated based on their source file, line number, and content. If the same example is used by multiple entities, they all point to the same Example node.

### Exploring the Graph

After running the example, you can explore the graph using:

1. **Neo4j Browser** (http://localhost:7474)
2. **Cypher Queries** (see example output for query templates)

Example queries:

```cypher
// Find all classes
MATCH (c:Class) RETURN c.name, c.api_path

// Get classes with their methods
MATCH (c:Class)-[:CONTAINS]->(m:Method)
RETURN c.name, collect(m.name) as methods

// Find shared examples
MATCH (e:Example)<-[:HAS_EXAMPLE]-(n)
WITH e, collect(n.name) as entities
WHERE size(entities) > 1
RETURN e.source_file, e.line, entities

// Get complete class structure with examples
MATCH (c:Class {name: 'PythonRepositoryProcessor'})
OPTIONAL MATCH (c)-[:CONTAINS]->(m:Method)
OPTIONAL MATCH (c)-[:HAS_EXAMPLE]->(ce:Example)
OPTIONAL MATCH (m)-[:HAS_EXAMPLE]->(me:Example)
RETURN c, m, ce, me
```

## Programmatic Usage

You can also use the Neo4j converter directly in your code:

```python
import asyncio
from pygrad.processor.processor import process_repository_to_neo4j

async def save_to_neo4j():
    stats = await process_repository_to_neo4j(
        repository_path="/path/to/repo",
        neo4j_uri="bolt://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="password",
        database="neo4j",
        clear_existing=True
    )
    print(f"Created {stats['classes']} classes, {stats['functions']} functions")

asyncio.run(save_to_neo4j())
```

Or use the lower-level API:

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

# Save to Neo4j
stats = processor.save_repository_to_neo4j(
    classes, functions,
    neo4j_uri="bolt://localhost:7687",
    neo4j_username="neo4j",
    neo4j_password="password"
)
```

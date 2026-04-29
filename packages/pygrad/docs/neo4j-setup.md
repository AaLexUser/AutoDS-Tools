# Neo4j Setup for PyGrad

This guide explains how to set up Neo4j for use with PyGrad's GraphRAG backend.

## Using Docker Compose (Recommended)

### Quick Start

1. **Start Neo4j**:
   ```bash
   docker-compose up -d
   ```

2. **Check status**:
   ```bash
   docker-compose ps
   ```

3. **View logs**:
   ```bash
   docker-compose logs -f neo4j
   ```

4. **Stop Neo4j**:
   ```bash
   docker-compose down
   ```

5. **Stop and remove data** (clean slate):
   ```bash
   docker-compose down -v
   ```

### Access Neo4j

- **Browser UI**: http://localhost:7474
- **Bolt Connection**: bolt://localhost:7687
- **Default Credentials**:
  - Username: `neo4j`
  - Password: `pleaseletmein`

### Configuration

The docker-compose.yml includes:

- **Neo4j 5.26.0**: Latest stable version
- **APOC Plugin**: Extended procedures and functions
- **Graph Data Science**: Advanced graph algorithms
- **Memory Settings**:
  - Page cache: 512MB
  - Heap: 512MB initial, 2GB max
- **Persistent Volumes**: Data, logs, imports, and plugins

### Environment Variables

The configuration matches `.env_example`:

```env
NEO4J_URI="bolt://localhost:7687"
NEO4J_USERNAME="neo4j"
NEO4J_PASSWORD="pleaseletmein"
NEO4J_DATABASE="neo4j"
```

## Manual Installation

### macOS (Homebrew)

```bash
brew install neo4j
neo4j start
```

### Linux (Debian/Ubuntu)

```bash
wget -O - https://debian.neo4j.com/neotechnology.gpg.key | sudo apt-key add -
echo 'deb https://debian.neo4j.com stable latest' | sudo tee /etc/apt/sources.list.d/neo4j.list
sudo apt-get update
sudo apt-get install neo4j
sudo systemctl start neo4j
```

### Windows

Download and install from: https://neo4j.com/download/

## Verifying Connection

Test your Neo4j connection:

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    "bolt://localhost:7687",
    auth=("neo4j", "pleaseletmein")
)

with driver.session() as session:
    result = session.run("RETURN 'Connection successful!' as message")
    print(result.single()["message"])

driver.close()
```

## Using with PyGrad

1. **Configure environment**:
   ```bash
   cp .env_example .env
   # Edit .env and set:
   SEARCH_BACKEND="neo4j-graphrag"
   ```

2. **Install dependencies**:
   ```bash
   pip install neo4j-graphrag>=0.9.0 httpx>=0.27.0
   ```

3. **Start Neo4j**:
   ```bash
   docker-compose up -d
   ```

4. **Add a repository**:
   ```bash
   pygrad add https://github.com/psf/requests
   ```

5. **Query the graph**:
   ```bash
   pygrad ask https://github.com/psf/requests "How do I make a POST request?"
   ```

## Monitoring and Management

### View Graph in Browser

1. Open http://localhost:7474
2. Connect with credentials
3. Run Cypher queries:

```cypher
// List all repositories
MATCH (n)
WHERE n.repository_id IS NOT NULL
RETURN DISTINCT n.repository_id, labels(n)[0] as type, count(*) as count

// View a specific repository structure
MATCH (n {repository_id: "psf-requests"})
RETURN labels(n)[0] as type, count(*) as count

// Find classes with examples
MATCH (c:Class {repository_id: "psf-requests"})-[:HAS_EXAMPLE]->(e:Example)
RETURN c.api_path, count(e) as example_count
ORDER BY example_count DESC
LIMIT 10
```

### Check Vector Indexes

```cypher
SHOW INDEXES
YIELD name, type, labelsOrTypes, properties
WHERE type = 'VECTOR'
RETURN *
```

### Database Statistics

```cypher
// Node counts by type and repository
MATCH (n)
WHERE n.repository_id IS NOT NULL
RETURN n.repository_id as repository, labels(n)[0] as type, count(*) as count
ORDER BY repository, type

// Relationship counts
MATCH ()-[r]->()
RETURN type(r) as relationship_type, count(*) as count
ORDER BY count DESC
```

## Troubleshooting

### Container won't start

Check logs:
```bash
docker-compose logs neo4j
```

### Memory issues

Adjust memory settings in `docker-compose.yml`:
```yaml
environment:
  - NEO4J_server_memory_heap_max__size=4G  # Increase if needed
```

### Connection refused

1. Ensure Neo4j is running: `docker-compose ps`
2. Check port availability: `lsof -i :7687`
3. Wait for startup: `docker-compose logs -f neo4j` (look for "Started")

### Clear all data

```bash
docker-compose down -v
docker-compose up -d
```

Or via Cypher:
```cypher
// WARNING: Deletes all data
MATCH (n) DETACH DELETE n
```

### Clean up specific repository

```bash
pygrad delete https://github.com/psf/requests
```

Or via Cypher:
```cypher
MATCH (n {repository_id: "psf-requests"})
DETACH DELETE n
```

## Production Considerations

For production deployments:

1. **Change default password**:
   ```yaml
   - NEO4J_AUTH=neo4j/your-secure-password
   ```

2. **Enable SSL/TLS**: Configure certificates and bolt+s:// protocol

3. **Increase memory**: Adjust heap and pagecache based on data size

4. **Set up backups**: Use Neo4j backup tools or volume snapshots

5. **Monitor performance**: Use Neo4j metrics and monitoring tools

6. **Network isolation**: Use Docker networks and firewall rules

## Resources

- [Neo4j Documentation](https://neo4j.com/docs/)
- [Cypher Query Language](https://neo4j.com/docs/cypher-manual/current/)
- [APOC Documentation](https://neo4j.com/labs/apoc/)
- [Graph Data Science](https://neo4j.com/docs/graph-data-science/current/)

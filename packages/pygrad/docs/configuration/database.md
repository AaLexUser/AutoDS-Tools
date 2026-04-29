# Database Configuration

Configure vector and graph databases for production deployments.

## Default Configuration

By default, Pygrad uses lightweight embedded databases:

| Database | Default | Purpose |
|----------|---------|---------|
| Vector DB | LanceDB | Embedding storage and search |
| Relational DB | SQLite | Metadata storage |
| Graph DB | NetworkX | Knowledge graph |

These defaults work well for development and single-user scenarios.

## Production Setup

For production deployments, use dedicated database servers.

### PostgreSQL with pgvector

PostgreSQL with the pgvector extension for vector storage:

```bash
# Vector and relational database
VECTOR_DB_PROVIDER="pgvector"
DB_PROVIDER="postgres"
DB_NAME="pygrad_db"
DB_HOST="localhost"
DB_PORT="5432"
DB_USERNAME="pygrad"
DB_PASSWORD="your-secure-password"
```

#### Setup pgvector

```sql
-- Create database
CREATE DATABASE pygrad_db;

-- Enable pgvector extension
CREATE EXTENSION vector;

-- Create user
CREATE USER pygrad WITH PASSWORD 'your-secure-password';
GRANT ALL PRIVILEGES ON DATABASE pygrad_db TO pygrad;
```

#### Docker Setup

```yaml
# docker-compose.yml
version: '3.8'
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: pygrad_db
      POSTGRES_USER: pygrad
      POSTGRES_PASSWORD: your-secure-password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

### Neo4j Graph Database

For advanced graph queries and visualization:

```bash
# Graph database
GRAPH_DATABASE_PROVIDER="neo4j"
GRAPH_DATABASE_URL="bolt://localhost:7687"
GRAPH_DATABASE_NAME="neo4j"
GRAPH_DATABASE_USERNAME="neo4j"
GRAPH_DATABASE_PASSWORD="your-secure-password"
```

#### Docker Setup

```yaml
# docker-compose.yml
version: '3.8'
services:
  neo4j:
    image: neo4j:5
    environment:
      NEO4J_AUTH: neo4j/your-secure-password
      NEO4J_PLUGINS: '["apoc"]'
    ports:
      - "7474:7474"  # Browser
      - "7687:7687"  # Bolt
    volumes:
      - neo4j_data:/data

volumes:
  neo4j_data:
```

### Qdrant Vector Database

High-performance vector database:

```bash
VECTOR_DB_PROVIDER="qdrant"
QDRANT_URL="http://localhost:6333"
QDRANT_API_KEY="your-api-key"  # Optional
```

#### Docker Setup

```yaml
# docker-compose.yml
version: '3.8'
services:
  qdrant:
    image: qdrant/qdrant
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage

volumes:
  qdrant_data:
```

## Full Production Configuration

Complete `.env` for production:

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

# Vector Database (pgvector)
VECTOR_DB_PROVIDER="pgvector"
DB_PROVIDER="postgres"
DB_NAME="pygrad_db"
DB_HOST="localhost"
DB_PORT="5432"
DB_USERNAME="pygrad"
DB_PASSWORD="your-secure-password"

# Graph Database (Neo4j)
GRAPH_DATABASE_PROVIDER="neo4j"
GRAPH_DATABASE_URL="bolt://localhost:7687"
GRAPH_DATABASE_NAME="neo4j"
GRAPH_DATABASE_USERNAME="neo4j"
GRAPH_DATABASE_PASSWORD="your-secure-password"

# Performance
TELEMETRY_DISABLED=true
```

## Docker Compose (All Services)

```yaml
# docker-compose.yml
version: '3.8'

services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: pygrad_db
      POSTGRES_USER: pygrad
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U pygrad"]
      interval: 5s
      timeout: 5s
      retries: 5

  neo4j:
    image: neo4j:5
    environment:
      NEO4J_AUTH: neo4j/${GRAPH_DATABASE_PASSWORD}
      NEO4J_PLUGINS: '["apoc"]'
    ports:
      - "7474:7474"
      - "7687:7687"
    volumes:
      - neo4j_data:/data
    healthcheck:
      test: ["CMD", "neo4j", "status"]
      interval: 10s
      timeout: 10s
      retries: 5

  ollama:
    image: ollama/ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

volumes:
  postgres_data:
  neo4j_data:
  ollama_data:
```

Start all services:

```bash
docker-compose up -d
```

## Data Persistence

### Storage Locations

| Component | Default Location |
|-----------|-----------------|
| Cloned repos | `~/.pygrad/repos/` |
| LanceDB data | `~/.cognee/` |
| SQLite database | `~/.cognee/` |

### Backup

For production, back up your databases regularly:

```bash
# PostgreSQL backup
pg_dump -U pygrad pygrad_db > backup.sql

# Neo4j backup
neo4j-admin database dump neo4j --to-path=/backups/
```

## Performance Tuning

### PostgreSQL

```sql
-- Increase work memory for vector operations
ALTER SYSTEM SET work_mem = '256MB';
ALTER SYSTEM SET maintenance_work_mem = '512MB';

-- Reload configuration
SELECT pg_reload_conf();
```

### Neo4j

```properties
# neo4j.conf
dbms.memory.heap.initial_size=512m
dbms.memory.heap.max_size=2g
dbms.memory.pagecache.size=512m
```

## Next Steps

- [Architecture overview](../architecture/index.md)
- [API reference](../api/index.md)
- [Examples](../examples/index.md)

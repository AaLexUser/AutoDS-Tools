"""Complete pipeline: Index a repository in Neo4j with embeddings.

This script combines all steps to fully index a repository:
1. Extract API elements and examples from the repository
2. Populate Neo4j graph database
3. Create vector indexes
4. Generate and store embeddings

Requirements:
    - Neo4j database running
    - LLM and embedding providers configured in .env

Usage:
    python examples/index_repository.py
"""

import asyncio
import os

from neo4j import GraphDatabase

from pygrad import get_repository_id
from pygrad.graphrag import (
    create_embedder_from_env,
    generate_and_store_embeddings,
    setup_vector_indexes,
)
from pygrad.processor import process_repository_to_neo4j


async def main():
    # Configuration
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "pleaseletmein")
    NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
    EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))

    #repository_path = "/home/stas/.autods/repos/sb-ai-lab/replay"
    repository_path = "/home/stas/.autods/repos/sb-ai-lab/lightautoml"
    repository_id = get_repository_id(repository_path)

    print("PyGrad Repository Indexing Pipeline")
    print("=" * 60)
    print(f"Repository: {repository_path}")
    print(f"Repository ID: {repository_id}")
    print(f"Neo4j URI: {NEO4J_URI}")
    print(f"Database: {NEO4J_DATABASE}")
    print("=" * 60)

    # Step 1: Populate Neo4j graph
    print("\n[1/3] Populating Neo4j graph...")
    stats = await process_repository_to_neo4j(
        repository_path=repository_path,
        repository_id=repository_id,
        neo4j_uri=NEO4J_URI,
        neo4j_username=NEO4J_USERNAME,
        neo4j_password=NEO4J_PASSWORD,
        database=NEO4J_DATABASE,
        clear_existing=True,
    )

    print(f"✓ Graph populated: {stats['classes']} classes, {stats['functions']} functions, "
          f"{stats['methods']} methods, {stats['examples']} examples")

    # Create driver for embedding steps
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

    try:
        # Step 2: Create vector indexes
        print("\n[2/3] Creating vector indexes...")
        setup_vector_indexes(
            driver=driver,
            repository_id=repository_id,
            dimensions=EMBEDDING_DIMENSIONS,
            database=NEO4J_DATABASE,
        )
        print("✓ Vector indexes created")

        # Step 3: Generate embeddings
        print("\n[3/3] Generating embeddings...")
        embedder = create_embedder_from_env()
        embedding_stats = await generate_and_store_embeddings(
            driver=driver,
            repository_id=repository_id,
            embedder=embedder,
            database=NEO4J_DATABASE,
        )

        print("✓ Embeddings generated:")
        for node_type, count in embedding_stats.items():
            print(f"  - {node_type}: {count} nodes")

    finally:
        driver.close()

    print("\n" + "=" * 60)
    print("✓ Indexing complete! Ready to answer questions.")
    print("\nTry: python examples/ask_simple.py")


if __name__ == "__main__":
    asyncio.run(main())

"""Minimal example: Ask a single question about a repository.

Usage:
    python examples/ask_simple.py
"""

import asyncio
import os

from neo4j import GraphDatabase

from pygrad import get_repository_id
from pygrad.graphrag import PyGradRAGPipeline


async def main():
    # Connect to Neo4j (using synchronous driver for neo4j-graphrag compatibility)
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(
            os.getenv("NEO4J_USERNAME", "neo4j"),
            os.getenv("NEO4J_PASSWORD", "pleaseletmein"),
        ),
    )

    try:
        # Create RAG pipeline for the replay repository
        repository_path = "/home/stas/.autods/repos/sb-ai-lab/replay"
        pipeline = PyGradRAGPipeline(
            driver=driver,
            repository_id=get_repository_id(repository_path),
            database=os.getenv("NEO4J_DATABASE", "neo4j"),
        )

        # Ask a question
        question = "How do I create a recommendation model?"
        print(f"Q: {question}\n")

        response = await pipeline.search(question, top_k=5)
        print(f"A: {response}")

    finally:
        driver.close()


if __name__ == "__main__":
    asyncio.run(main())

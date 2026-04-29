"""Pygrad - Graph RAG API Doc library for building searchable knowledge graphs."""

from __future__ import annotations

import builtins
import contextlib
import os
from pathlib import Path
from typing import Any, cast

from dotenv import load_dotenv
from neo4j import GraphDatabase

from pygrad.cognee_search import execute_cognee_search
from pygrad.common.log import get_logger
from pygrad.config import REPO_STORAGE, ensure_storage_exists
from pygrad.graphrag.common import NODE_LABELS
from pygrad.graphrag.config import SearchBackend, get_neo4j_config, get_search_backend
from pygrad.graphrag.embeddings import (
    create_embedder_from_env,
    generate_and_store_embeddings,
    get_embedding_dimensions_from_env,
    setup_vector_indexes,
    validate_embedding_dimensions_for_index,
)
from pygrad.graphrag.pipeline import PyGradRAGPipeline
from pygrad.processor.processor import process_repository, process_repository_to_neo4j
from pygrad.prompt_store import prompt_store
from pygrad.repository import clone_repository, get_repository_id
from pygrad.xmlapi import extract_entities

load_dotenv()

logger = get_logger(__name__)


def _get_cognee_runtime():
    """Import Cognee runtime dependencies only when the backend needs them."""
    import cognee
    from cognee.modules.engine.operations.setup import setup

    return cognee, setup


def _get_visualize_graph():
    """Import Cognee visualization only when requested."""
    from cognee.api.v1.visualize.visualize import visualize_graph

    return visualize_graph


async def add(url: str) -> None:
    """Add a repository to the knowledge graph.

    This function clones the repository (if not already cached), parses all Python
    files using TreeSitter, extracts API documentation, and indexes it into the
    knowledge graph.

    Args:
        url: GitHub repository URL (e.g., https://github.com/owner/repo)

    Example:
        >>> import pygrad as pg
        >>> await pg.add("https://github.com/psf/requests")
    """
    backend = get_search_backend()
    repo_id = get_repository_id(url)

    if backend == SearchBackend.COGNEE:
        _, setup = _get_cognee_runtime()
        await setup()
        xml_api_path = await _create_xml_api_doc(url)
        await _cognee_add_xml_api(xml_api_path, repo_id)

    elif backend == SearchBackend.NEO4J_GRAPHRAG:
        # Clone repository
        ensure_storage_exists()
        repo_path = Path(REPO_STORAGE) / repo_id
        if not repo_path.exists():
            clone_repository(url, repo_path)

        # Get Neo4j configuration
        neo4j_config = get_neo4j_config()

        # Process repository to Neo4j
        stats = await process_repository_to_neo4j(
            repository_path=str(repo_path),
            neo4j_uri=neo4j_config.uri,
            neo4j_username=neo4j_config.username,
            neo4j_password=neo4j_config.password,
            repository_id=repo_id,
            database=neo4j_config.database,
            clear_existing=False,
        )

        print(
            f"Created {stats['classes']} classes, {stats['functions']} functions, "
            f"{stats['methods']} methods, {stats['examples']} examples"
        )

        # Setup vector indexes and generate embeddings
        driver = GraphDatabase.driver(
            neo4j_config.uri,
            auth=(neo4j_config.username, neo4j_config.password),
        )

        try:
            dimensions = get_embedding_dimensions_from_env()
            embedder = create_embedder_from_env()
            validate_embedding_dimensions_for_index(dimensions, embedder)
            env_raw = os.getenv("EMBEDDING_DIMENSIONS")
            if env_raw is None:
                logger.info(
                    "Embedding index dimensions: {} (EMBEDDING_DIMENSIONS not set; using default)",
                    dimensions,
                )
            else:
                logger.info(
                    "Embedding index dimensions: {} (EMBEDDING_DIMENSIONS={})",
                    dimensions,
                    env_raw,
                )

            # Create vector indexes
            setup_vector_indexes(
                driver=driver,
                repository_id=repo_id,
                dimensions=dimensions,
                database=neo4j_config.database,
            )
            print(f"Created vector indexes for repository: {repo_id}")

            embedding_stats = await generate_and_store_embeddings(
                driver=driver,
                repository_id=repo_id,
                embedder=embedder,
                database=neo4j_config.database,
            )
            print(f"Generated embeddings: {embedding_stats}")

        finally:
            driver.close()


async def search(url: str, query: str) -> str:
    """Search a repository's knowledge graph using natural language.

    Uses Graph RAG (Retrieval Augmented Generation) to search the knowledge graph
    and generate contextual answers based on the indexed API documentation.

    Args:
        url: GitHub repository URL
        query: Natural language query

    Returns:
        Query result as a string

    Example:
        >>> import pygrad as pg
        >>> result = await pg.search(
        ...     "https://github.com/psf/requests",
        ...     "How do I make a POST request with JSON?"
        ... )
        >>> print(result)
    """
    backend = get_search_backend()
    repo_id = get_repository_id(url)

    if backend == SearchBackend.COGNEE:
        dataset = await get_dataset(repo_id)

        if not dataset:
            return "The library is not yet indexed."

        system_prompt = prompt_store.load("grad.md")
        return await execute_cognee_search(dataset.id, query, system_prompt)

    elif backend == SearchBackend.NEO4J_GRAPHRAG:
        # Get Neo4j configuration
        neo4j_config = get_neo4j_config()

        # Create driver
        driver = GraphDatabase.driver(
            neo4j_config.uri,
            auth=(neo4j_config.username, neo4j_config.password),
        )

        try:
            # Check if repository exists
            with driver.session(database=neo4j_config.database) as session:
                result = session.run(
                    "MATCH (n {repository_id: $repo_id}) RETURN count(n) as count",
                    repo_id=repo_id,
                )
                row = result.single()
                count = row["count"] if row is not None else 0
                logger.debug("Repository {}: {} nodes in graph", repo_id, count)
                if count == 0:
                    return "The library is not yet indexed."

            # Create pipeline and search
            pipeline = PyGradRAGPipeline(
                driver=driver,
                repository_id=repo_id,
                database=neo4j_config.database,
            )

            response = await pipeline.search(query, top_k=5)
            logger.debug("Search response: {} chars", len(response))
            return response

        finally:
            driver.close()

    return "No results found."


async def visualize(path: str = "./pygrad.html") -> str:
    """Export the knowledge graph as an interactive HTML visualization.

    Args:
        path: Output file path (default: "./pygrad.html")

    Returns:
        Path to the generated HTML file

    Example:
        >>> import pygrad as pg
        >>> await pg.visualize("./knowledge-graph.html")
    """
    _, setup = _get_cognee_runtime()
    visualize_graph = _get_visualize_graph()
    await setup()
    await visualize_graph(path)
    return path


async def get_dataset(dataset_name: str, default: Any = None) -> Any:
    """Get a dataset by name.

    Args:
        dataset_name: Name of the dataset (repository ID)
        default: Default value if dataset not found

    Returns:
        Dataset object or default if not found

    Example:
        >>> import pygrad as pg
        >>> from pygrad import get_repository_id
        >>> repo_id = get_repository_id("https://github.com/owner/repo")
        >>> dataset = await pg.get_dataset(repo_id)
    """
    datasets = await list_datasets()
    for dataset in datasets:
        if dataset.name.lower() == dataset_name.lower():
            return dataset
    return default


async def delete(url: str) -> None:
    """Delete a repository from the knowledge graph.

    This removes the indexed data but does not delete the cached repository files.

    Args:
        url: GitHub repository URL

    Example:
        >>> import pygrad as pg
        >>> await pg.delete("https://github.com/owner/repo")
    """
    backend = get_search_backend()
    repo_id = get_repository_id(url)

    if backend == SearchBackend.COGNEE:
        cognee, _ = _get_cognee_runtime()
        dataset = await get_dataset(repo_id)
        if dataset:
            await cognee.datasets.empty_dataset(dataset.id)

    elif backend == SearchBackend.NEO4J_GRAPHRAG:
        # Get Neo4j configuration
        neo4j_config = get_neo4j_config()

        # Create driver
        driver = GraphDatabase.driver(
            neo4j_config.uri,
            auth=(neo4j_config.username, neo4j_config.password),
        )

        try:
            with driver.session(database=neo4j_config.database) as session:
                # Delete all nodes for this repository
                session.run(
                    "MATCH (n {repository_id: $repo_id}) DETACH DELETE n",
                    repo_id=repo_id,
                )

                # Drop vector indexes for this repository
                for node_type in NODE_LABELS:
                    index_name = f"{repo_id}_{node_type}_embeddings"
                    with contextlib.suppress(Exception):
                        session.run(cast(Any, f"DROP INDEX `{index_name}` IF EXISTS"))

        finally:
            driver.close()


async def list_datasets() -> builtins.list[Any]:
    """List all indexed datasets (repositories).

    Returns:
        List of dataset objects with name and id attributes

    Example:
        >>> import pygrad as pg
        >>> datasets = await pg.list()
        >>> for ds in datasets:
        ...     print(ds.name)
    """
    backend = get_search_backend()

    if backend == SearchBackend.COGNEE:
        cognee, setup = _get_cognee_runtime()
        await setup()
        return await cognee.datasets.list_datasets()

    elif backend == SearchBackend.NEO4J_GRAPHRAG:
        # Get Neo4j configuration
        neo4j_config = get_neo4j_config()

        # Create driver
        driver = GraphDatabase.driver(
            neo4j_config.uri,
            auth=(neo4j_config.username, neo4j_config.password),
        )

        try:
            with driver.session(database=neo4j_config.database) as session:
                # Query for distinct repository_ids
                result = session.run(
                    """
                    MATCH (n)
                    WHERE n.repository_id IS NOT NULL
                    RETURN DISTINCT n.repository_id as repository_id
                    ORDER BY n.repository_id
                    """
                )

                # Create dataset-like objects
                datasets = []
                for record in result:
                    repo_id = record["repository_id"]
                    # Create a simple object with name and id attributes
                    dataset = type(
                        "Dataset",
                        (),
                        {
                            "name": repo_id,
                            "id": repo_id,
                        },
                    )()
                    datasets.append(dataset)

                return datasets

        finally:
            driver.close()

    return []


# Alias for numpy-style API (pg.list())
list = list_datasets


async def _create_xml_api_doc(url: str) -> Path:
    """Create XML API documentation for a repository."""
    ensure_storage_exists()
    repo_path = Path(REPO_STORAGE) / get_repository_id(url)
    xml_api_filename = "api.xml"
    xml_api_path = repo_path / xml_api_filename

    if not xml_api_path.exists():
        if not repo_path.exists():
            clone_repository(url, repo_path)
        await process_repository(
            repository_path=str(repo_path),
            output_file=xml_api_filename,
        )
    return xml_api_path


def _split_xml_api(xml_api_path: Path) -> builtins.list[str]:
    """Split XML API into documents for indexing."""
    classes, methods, functions, examples = extract_entities(xml_api_path)
    return [*classes, *methods, *functions, *examples]


async def _cognee_add_xml_api(xml_api_path: Path, dataset_name: str) -> None:
    """Add XML API to Cognee knowledge graph."""
    import cognee

    custom_prompt = """
    Extract methods, functions and classes as entities, add their parameters to description.
    Connect classes to methods with the relationship "has_method".
    Connect methods to classes with the relationship "belongs_to".
    Connect examples to methods, classes, and functions that are used in this example with the relationship "is_used".
    """
    documents = _split_xml_api(xml_api_path)
    await cognee.add(
        documents,
        dataset_name=dataset_name,
        preferred_loaders=["text_loader"],
        data_per_batch=1,
    )
    await cognee.cognify(data_per_batch=1, custom_prompt=custom_prompt)

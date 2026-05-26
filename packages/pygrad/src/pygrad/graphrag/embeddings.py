"""Embedding implementations for neo4j-graphrag integration."""

import contextlib
import os
from typing import Any, cast

from neo4j import Driver
from neo4j_graphrag.embeddings import Embedder
from tqdm import trange

from pygrad.graphrag.common import NODE_LABELS
from pygrad.graphrag.http_client import create_sync_client, post_json_with_retries
from pygrad.processor.api_tier import infer_topic_hints, tier_label_for_embedding

_DEFAULT_EMBEDDING_DIMENSIONS = 768
_EXAMPLE_CODE_LIMIT = 1500


def build_api_embedding_text(
    api_path: str,
    name: str,
    description: str,
    node_type: str,
    api_tier: str | None = None,
    header: str | None = None,
    init_parameters: str | None = None,
) -> str:
    """Build rich embedding text for API nodes."""
    tier = api_tier or "api"
    tier_label = tier_label_for_embedding(tier)
    topic_hints = infer_topic_hints(description)

    parts = [f"{name} ({tier_label})", f"API: {api_path}"]
    if topic_hints:
        parts.append(topic_hints)
    if init_parameters:
        parts.append(f"Constructor: {name}({init_parameters})")
    if header:
        parts.append(f"Signature: {header}")
    if description:
        parts.append(description)
    return "\n".join(parts)


def build_example_embedding_text(
    source_file: str,
    source_code: str,
    line: str | int | None = None,
    example_type: str | None = None,
    header: str | None = None,
    description: str | None = None,
) -> str:
    """Build rich embedding text for usage examples."""
    parts = ["Usage example"]
    if example_type:
        parts.append(f"Type: {example_type}")
    if header:
        parts.append(f"Topic: {header}")
    if description and description != header:
        parts.append(description)
    parts.append(f"Source: {source_file}:{line or '?'}")
    code_snippet = source_code[:_EXAMPLE_CODE_LIMIT] if source_code else ""
    if code_snippet:
        parts.append(code_snippet)
    return "\n".join(parts)


def get_embedding_dimensions_from_env() -> int:
    """Return vector size from ``EMBEDDING_DIMENSIONS``"""
    return int(os.getenv("EMBEDDING_DIMENSIONS", str(_DEFAULT_EMBEDDING_DIMENSIONS)))


def validate_embedding_dimensions_for_index(dimensions: int, embedder: Embedder) -> None:
    """Raise if an embedder that declares width disagrees with ``dimensions``."""
    if isinstance(embedder, CustomEmbedder) and embedder.dimensions != dimensions:
        msg = (
            f"EMBEDDING_DIMENSIONS ({dimensions}) must match CustomEmbedder.dimensions "
            f"({embedder.dimensions}); both should come from the same env configuration."
        )
        raise ValueError(msg)


class CustomEmbedder(Embedder):
    """Custom embedder implementation for OpenAI-compatible embedding APIs.

    Implements the neo4j-graphrag Embedder interface for custom embedding endpoints.
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        endpoint: str,
        dimensions: int = 768,
    ):
        """Initialize CustomEmbedder.

        Args:
            model: Embedding model name
            api_key: API key for authentication
            endpoint: API endpoint URL
            dimensions: Embedding vector dimensions
        """
        self.model = model
        self.api_key = api_key
        self.endpoint = endpoint
        self.dimensions = dimensions

    def embed_query(self, text: str, **kwargs: Any) -> list[float]:
        """Generate embedding for a query text.

        Args:
            text: Text to embed
            **kwargs: Extra JSON fields for the embedding API (e.g. OpenAI-compatible).
                ``dimensions`` defaults to ``self.dimensions`` but can be overridden.

        Returns:
            Embedding vector as list of floats
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": self.model,
            "input": text,
            "dimensions": self.dimensions,
        }
        payload.update(kwargs)

        with create_sync_client(timeout=60.0) as client:
            response = post_json_with_retries(
                client,
                self.endpoint,
                json=payload,
                headers=headers,
            )

            # Check if response is empty
            if not response.content:
                raise ValueError(f"Empty response from embedding endpoint: {self.endpoint}")

            try:
                data = response.json()
            except Exception as e:
                raise ValueError(
                    f"Failed to parse JSON from embedding endpoint {self.endpoint}. "
                    f"Response status: {response.status_code}, "
                    f"Content: {response.text[:200]}"
                ) from e

        # Handle OpenAI-compatible response format
        if "data" in data and len(data["data"]) > 0:
            return data["data"][0]["embedding"]
        # Handle Ollama /api/embed response format (returns "embeddings" array)
        elif "embeddings" in data and len(data["embeddings"]) > 0:
            return data["embeddings"][0]
        # Handle Ollama /api/embeddings response format (returns single "embedding")
        elif "embedding" in data:
            return data["embedding"]
        else:
            raise ValueError(f"Unexpected embedding response format: {data}")


def create_embedder_from_env() -> Embedder:
    """Create embedder instance from environment variables.

    Supports providers: custom, ollama, openai

    Environment variables:
        EMBEDDING_PROVIDER: Provider name (custom, ollama, openai)
        EMBEDDING_MODEL: Model name
        EMBEDDING_ENDPOINT: API endpoint URL (for custom/ollama)
        EMBEDDING_DIMENSIONS: Vector dimensions
        LLM_API_KEY: API key (reused for embeddings with openai/custom)

    Returns:
        Embedder implementation

    Raises:
        ValueError: If required environment variables are missing
        ImportError: If provider-specific package is not installed
    """
    provider = os.getenv("EMBEDDING_PROVIDER", "").lower()
    model = os.getenv("EMBEDDING_MODEL")
    endpoint = os.getenv("EMBEDDING_ENDPOINT")
    dimensions = get_embedding_dimensions_from_env()
    # Try EMBEDDING_API_KEY first, fall back to LLM_API_KEY
    api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("LLM_API_KEY")

    if not provider:
        raise ValueError("EMBEDDING_PROVIDER environment variable is required")
    if not model:
        raise ValueError("EMBEDDING_MODEL environment variable is required")

    if provider == "custom":
        if not api_key:
            raise ValueError("EMBEDDING_API_KEY or LLM_API_KEY environment variable is required for custom provider")
        if not endpoint:
            raise ValueError("EMBEDDING_ENDPOINT environment variable is required for custom provider")

        return CustomEmbedder(
            model=model,
            api_key=api_key,
            endpoint=endpoint,
            dimensions=dimensions,
        )

    elif provider == "ollama":
        try:
            from neo4j_graphrag.embeddings import OllamaEmbeddings
        except ImportError as e:
            raise ImportError("Ollama support requires: pip install neo4j-graphrag[ollama]") from e

        return OllamaEmbeddings(
            model=model,
            host=endpoint or "http://localhost:11434",
        )

    elif provider == "openai":
        try:
            from neo4j_graphrag.embeddings import OpenAIEmbeddings
        except ImportError as e:
            raise ImportError("OpenAI support requires: pip install neo4j-graphrag[openai]") from e

        if not api_key:
            raise ValueError("EMBEDDING_API_KEY or LLM_API_KEY environment variable is required for openai provider")

        return OpenAIEmbeddings(
            model=model,
            api_key=api_key,
            base_url=endpoint,
        )

    else:
        raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {provider}. Supported providers: custom, ollama, openai")


def setup_vector_indexes(
    driver: Driver,
    repository_id: str,
    dimensions: int,
    database: str = "neo4j",
) -> None:
    """Create vector indexes for Class, Function, Method, and Example nodes.

    Args:
        driver: Neo4j driver instance
        repository_id: Repository identifier for index naming
        dimensions: Embedding vector dimensions
        database: Database name (default: "neo4j")
    """

    with driver.session(database=database) as session:
        for node_type in NODE_LABELS:
            index_name = f"{repository_id}_{node_type}_embeddings"

            # Drop existing index if present (escape with backticks for special chars)
            with contextlib.suppress(Exception):
                session.run(cast(Any, f"DROP INDEX `{index_name}` IF EXISTS"))

            # Create vector index (escape with backticks for special chars)
            query = f"""
            CREATE VECTOR INDEX `{index_name}` IF NOT EXISTS
            FOR (n:{node_type})
            ON n.embedding
            OPTIONS {{
                indexConfig: {{
                    `vector.dimensions`: {dimensions},
                    `vector.similarity_function`: 'cosine'
                }}
            }}
            """
            session.run(cast(Any, query))


async def generate_and_store_embeddings(
    driver: Driver,
    repository_id: str,
    embedder: Embedder,
    database: str = "neo4j",
    batch_size: int = 50,
) -> dict[str, int]:
    """Generate and store embeddings for nodes without them.

    Args:
        driver: Neo4j driver instance
        repository_id: Repository identifier
        embedder: Embedder instance for generating embeddings
        database: Database name (default: "neo4j")
        batch_size: Number of nodes to process per batch (default: 50)

    Returns:
        Dictionary with counts of embedded nodes by type
    """
    stats = {}

    with driver.session(database=database) as session:
        for node_type in NODE_LABELS:
            print(f"embedding {node_type} nodes")
            # Query nodes without embeddings
            if node_type == "Example":
                query = f"""
                MATCH (n:{node_type} {{repository_id: $repository_id}})
                WHERE n.embedding IS NULL
                RETURN n.source_file as source_file, n.source_code as source_code,
                       n.line as line, n.example_type as example_type,
                       n.header as header, n.description as description,
                       elementId(n) as id
                """
            else:
                query = f"""
                MATCH (n:{node_type} {{repository_id: $repository_id}})
                WHERE n.embedding IS NULL
                RETURN n.api_path as api_path, n.name as name,
                       n.description as description, n.api_tier as api_tier,
                       n.header as header, n.init_parameters as init_parameters,
                       elementId(n) as id
                """

            result = session.run(cast(Any, query), repository_id=repository_id)
            nodes = list(result)

            count = 0
            for i in trange(0, len(nodes), batch_size):
                batch = nodes[i : i + batch_size]

                for node in batch:
                    if node_type == "Example":
                        text = build_example_embedding_text(
                            source_file=node.get("source_file", ""),
                            source_code=node.get("source_code", ""),
                            line=node.get("line"),
                            example_type=node.get("example_type"),
                            header=node.get("header"),
                            description=node.get("description"),
                        )
                    else:
                        text = build_api_embedding_text(
                            api_path=node["api_path"],
                            name=node.get("name", ""),
                            description=node.get("description") or "",
                            node_type=node_type,
                            api_tier=node.get("api_tier"),
                            header=node.get("header"),
                            init_parameters=node.get("init_parameters"),
                        )

                    embedding = embedder.embed_query(text)

                    # Store embedding
                    update_query = """
                    MATCH (n)
                    WHERE elementId(n) = $id
                    SET n.embedding = $embedding
                    """
                    session.run(
                        update_query,
                        id=node["id"],
                        embedding=embedding,
                    )
                    count += 1

            stats[node_type] = count

    return stats

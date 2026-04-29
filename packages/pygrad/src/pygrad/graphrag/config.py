"""Configuration for GraphRAG backends."""

import os
from dataclasses import dataclass
from enum import Enum


class SearchBackend(Enum):
    """Supported search backends."""

    COGNEE = "cognee"
    NEO4J_GRAPHRAG = "neo4j-graphrag"


@dataclass
class Neo4jConfig:
    """Neo4j connection configuration."""

    uri: str
    username: str
    password: str
    database: str = "neo4j"

    @classmethod
    def from_env(cls) -> "Neo4jConfig":
        """Create Neo4j configuration from environment variables.

        Returns:
            Neo4jConfig instance

        Raises:
            ValueError: If required environment variables are missing
        """
        uri = os.getenv("NEO4J_URI")
        username = os.getenv("NEO4J_USERNAME")
        password = os.getenv("NEO4J_PASSWORD")
        database = os.getenv("NEO4J_DATABASE", "neo4j")

        if not uri:
            raise ValueError("NEO4J_URI environment variable is required")
        if not username:
            raise ValueError("NEO4J_USERNAME environment variable is required")
        if not password:
            raise ValueError("NEO4J_PASSWORD environment variable is required")

        return cls(uri=uri, username=username, password=password, database=database)


def get_search_backend() -> SearchBackend:
    """Get the configured search backend from environment.

    Returns:
        SearchBackend enum value

    Raises:
        ValueError: If SEARCH_BACKEND has an invalid value
    """
    backend_str = os.getenv("SEARCH_BACKEND", "cognee").lower()

    try:
        return SearchBackend(backend_str)
    except ValueError:
        valid_values = [b.value for b in SearchBackend]
        raise ValueError(
            f"Invalid SEARCH_BACKEND value: {backend_str}. Must be one of: {', '.join(valid_values)}"
        ) from None


def get_neo4j_config() -> Neo4jConfig:
    """Get Neo4j configuration from environment.

    Returns:
        Neo4jConfig instance

    Raises:
        ValueError: If required environment variables are missing
    """
    return Neo4jConfig.from_env()

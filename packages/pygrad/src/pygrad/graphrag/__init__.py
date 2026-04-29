"""Neo4j GraphRAG integration module.

This module provides an alternative search backend using neo4j-graphrag-python
with full repository isolation support.
"""

from pygrad.graphrag.config import (
    Neo4jConfig,
    SearchBackend,
    get_neo4j_config,
    get_search_backend,
)
from pygrad.graphrag.embeddings import (
    CustomEmbedder,
    create_embedder_from_env,
    generate_and_store_embeddings,
    setup_vector_indexes,
)
from pygrad.graphrag.llm import CustomAPILLM, create_llm_from_env
from pygrad.graphrag.pipeline import PyGradRAGPipeline
from pygrad.graphrag.retriever import MultiIndexRetriever, create_repository_retriever

__all__ = [
    "CustomAPILLM",
    "CustomEmbedder",
    "MultiIndexRetriever",
    "Neo4jConfig",
    "PyGradRAGPipeline",
    "SearchBackend",
    "create_embedder_from_env",
    "create_llm_from_env",
    "create_repository_retriever",
    "generate_and_store_embeddings",
    "get_neo4j_config",
    "get_search_backend",
    "setup_vector_indexes",
]

"""RAG pipeline implementation for neo4j-graphrag."""

import httpx
from neo4j import Driver

from pygrad.common.log import get_logger
from pygrad.graphrag.embeddings import create_embedder_from_env
from pygrad.graphrag.llm import create_llm_from_env
from pygrad.graphrag.retriever import MultiIndexRetriever
from pygrad.prompt_store import prompt_store

logger = get_logger(__name__)


class PyGradRAGPipeline:
    """RAG pipeline for querying repository knowledge graphs."""

    def __init__(
        self,
        driver: Driver,
        repository_id: str,
        database: str = "neo4j",
    ):
        """Initialize RAG pipeline.

        Args:
            driver: Neo4j driver instance
            repository_id: Repository identifier
            database: Database name (default: "neo4j")
        """
        self.driver = driver
        self.repository_id = repository_id
        self.database = database

        # Create LLM and embedder from environment
        self.llm = create_llm_from_env()
        self.embedder = create_embedder_from_env()

        # Create retriever
        self.retriever = MultiIndexRetriever(
            driver=driver,
            repository_id=repository_id,
            embedder=self.embedder,
            database=database,
        )

        # Load system prompt
        self.system_prompt = prompt_store.load("grad.md")

    async def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> str:
        """Search repository and generate response.

        Args:
            query: User query
            top_k: Number of context items to retrieve (default: 5)

        Returns:
            Generated response text
        """
        # Retrieve relevant context
        context_items = await self.retriever.search(
            query_text=query,
            top_k=top_k,
        )

        if not context_items:
            return "No relevant information found in the repository."

        # Build context string
        context = "\n\n".join(context_items)

        # Build full prompt
        full_prompt = f"""{self.system_prompt}

# Context

The following information was retrieved from the repository:

{context}

# User Query

{query}

# Instructions

Based on the context provided above, answer the user's query. Include relevant code examples from the context when applicable.
"""

        try:
            response = await self.llm.ainvoke(full_prompt)
            if not response.content:
                logger.error("LLM returned empty content for query: {}", query[:100])
                return "LLM returned an empty response. Try again or check LLM configuration."
            return response.content
        except (TimeoutError, httpx.TimeoutException):
            logger.error("LLM request timed out")
            return "LLM request timed out. Consider increasing the timeout or using a faster model."
        except Exception as e:
            logger.error("LLM error: {}: {}", type(e).__name__, e)
            return f"Error generating response: {type(e).__name__}: {e}"

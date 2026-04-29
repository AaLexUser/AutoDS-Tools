"""Retriever implementations for neo4j-graphrag integration."""

import contextlib

from neo4j import Driver, Record
from neo4j_graphrag.embeddings import Embedder
from neo4j_graphrag.retrievers import VectorCypherRetriever
from neo4j_graphrag.types import RetrieverResultItem

from pygrad.common.log import get_logger
from pygrad.graphrag.common import NODE_LABELS

logger = get_logger(__name__)


def create_repository_retriever(
    driver: Driver,
    repository_id: str,
    embedder: Embedder,
    node_type: str,
    database: str = "neo4j",
) -> VectorCypherRetriever:
    """Create a VectorCypherRetriever for a specific node type and repository.

    Args:
        driver: Neo4j driver instance
        repository_id: Repository identifier for filtering
        embedder: Embedder instance for query embedding
        node_type: Node type to search (Class, Function, Method, Example)
        database: Database name (default: "neo4j")

    Returns:
        VectorCypherRetriever instance
    """
    index_name = f"{repository_id}_{node_type}_embeddings"

    # Different query structure for Example nodes
    if node_type == "Example":
        retrieval_query = """
        // node is provided by the base vector search
        WHERE node.repository_id = $repository_id
        RETURN {
            source_file: node.source_file,
            source_code: node.source_code,
            line: node.line
        } AS result, score
        """
    else:
        # Custom Cypher query with repository filtering and graph traversal for API elements
        retrieval_query = """
        // node is provided by the base vector search
        WHERE node.repository_id = $repository_id

        // Traverse to examples and methods
        OPTIONAL MATCH (node)-[:HAS_EXAMPLE]->(example:Example)
        WHERE example.repository_id = $repository_id
        OPTIONAL MATCH (node)-[:CONTAINS]->(method:Method)
        WHERE method.repository_id = $repository_id

        WITH node, score,
             collect(DISTINCT {
                 source_file: example.source_file,
                 source_code: example.source_code,
                 line: example.line
             }) AS examples,
             collect(DISTINCT {
                 name: method.name,
                 api_path: method.api_path,
                 description: method.description,
                 header: method.header
             }) AS methods

        RETURN {
            api_path: node.api_path,
            name: node.name,
            description: node.description,
            header: node.header,
            examples: [ex IN examples WHERE ex.source_code IS NOT NULL],
            methods: [m IN methods WHERE m.name IS NOT NULL]
        } AS result, score
        """

    # Result formatter to convert to LLM-ready text
    def format_result(record: Record) -> RetrieverResultItem:
        """Format retrieval result as RetrieverResultItem for LLM context."""
        result = record.get("result") or {}
        score = record.get("score", 0.0)

        output = []

        # Format differently for Example nodes vs API elements
        if node_type == "Example":
            source_file = result.get("source_file", "unknown")
            line = result.get("line", "?")
            source_code = result.get("source_code", "")

            output.append(f"## Example from {source_file}:{line} (relevance: {score:.3f})")
            output.append(f"\n```python\n{source_code}\n```")
        else:
            output.append(f"## {result.get('api_path', 'Unknown')} (relevance: {score:.3f})")

            if result.get("description"):
                output.append(f"\n**Description:** {result['description']}")

            if result.get("header"):
                output.append(f"\n**Signature:** `{result['header']}`")

            # Add methods if present (for Class nodes)
            methods = result.get("methods", [])
            if methods:
                output.append("\n**Methods:**")
                for method in methods[:5]:  # Limit to top 5 methods
                    output.append(f"\n- `{method['api_path']}`: {method.get('description', 'No description')}")

            # Add examples if present
            examples = result.get("examples", [])
            if examples:
                output.append("\n**Usage Examples:**")
                for i, example in enumerate(examples[:3], 1):  # Limit to top 3 examples
                    output.append(
                        f"\n**Example {i}** (from {example.get('source_file', 'unknown')}:{example.get('line', '?')}):"
                    )
                    output.append(f"```python\n{example.get('source_code', '')}\n```")

        content = "\n".join(output)
        return RetrieverResultItem(content=content, metadata={"score": score, "node_type": node_type})

    return VectorCypherRetriever(
        driver=driver,
        index_name=index_name,
        embedder=embedder,
        retrieval_query=retrieval_query,
        result_formatter=format_result,
        neo4j_database=database,
    )


class MultiIndexRetriever:
    """Retriever that searches across multiple node type indexes.

    Combines results from Class, Function, Method, and Example indexes.
    """

    def __init__(
        self,
        driver: Driver,
        repository_id: str,
        embedder: Embedder,
        database: str = "neo4j",
    ):
        """Initialize MultiIndexRetriever.

        Args:
            driver: Neo4j driver instance
            repository_id: Repository identifier
            embedder: Embedder instance
            database: Database name (default: "neo4j")
        """
        self.driver = driver
        self.repository_id = repository_id
        self.embedder = embedder
        self.database = database

        # Create retrievers for each node type
        self.retrievers = {}
        for node_label in NODE_LABELS:
            try:
                self.retrievers[node_label] = create_repository_retriever(
                    driver=driver,
                    repository_id=repository_id,
                    embedder=embedder,
                    node_type=node_label,
                    database=database,
                )
            except Exception as e:
                logger.warning("Could not create retriever for {}: {}", node_label, e)

    async def search(
        self,
        query_text: str,
        top_k: int = 5,
    ) -> list[str]:
        """Search across all node types and return combined results.

        Args:
            query_text: Query text
            top_k: Number of results per node type (default: 5)

        Returns:
            List of formatted result strings
        """
        all_results = []

        # Search each node type
        for node_type, retriever in self.retrievers.items():
            try:
                results = retriever.search(
                    query_text=query_text,
                    top_k=top_k,
                    query_params={"repository_id": self.repository_id},
                )
                logger.debug(
                    "Retrieved {} items for {}",
                    len(results.items),
                    node_type,
                )
                all_results.extend(results.items)
            except Exception as e:
                logger.warning("Search failed for {}: {}", node_type, e)

        def _item_score(item: RetrieverResultItem) -> float:
            meta = item.metadata or {}
            s = meta.get("score")
            return float(s) if s is not None else 0.0

        with contextlib.suppress(Exception):
            all_results.sort(key=_item_score, reverse=True)

        # Format and deduplicate results
        formatted = []
        seen = set()
        for result in all_results[:top_k]:
            content = result.content if hasattr(result, "content") else str(result)

            # Simple deduplication based on content hash
            content_hash = hash(content[:100])  # Hash first 100 chars
            if content_hash not in seen:
                seen.add(content_hash)
                formatted.append(content)

        return formatted[:top_k]

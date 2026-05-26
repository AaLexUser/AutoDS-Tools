"""Retriever implementations for neo4j-graphrag integration."""

from neo4j import Driver, Record
from neo4j_graphrag.embeddings import Embedder
from neo4j_graphrag.retrievers import VectorCypherRetriever
from neo4j_graphrag.types import RetrieverResultItem

from pygrad.common.log import get_logger
from pygrad.graphrag.common import NODE_LABELS
from pygrad.graphrag.fusion import reciprocal_rank_fusion
from pygrad.processor.api_tier import classify_api_tier

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

    if node_type == "Example":
        retrieval_query = """
        // node is provided by the base vector search
        WHERE node.repository_id = $repository_id
        RETURN {
            source_file: node.source_file,
            source_code: node.source_code,
            line: node.line,
            example_type: node.example_type,
            header: node.header,
            description: node.description,
            api_tier: node.api_tier
        } AS result, score
        """
    else:
        retrieval_query = """
        // node is provided by the base vector search
        WHERE node.repository_id = $repository_id

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
            api_tier: node.api_tier,
            examples: [ex IN examples WHERE ex.source_code IS NOT NULL],
            methods: [m IN methods WHERE m.name IS NOT NULL]
        } AS result, score
        """

    def format_result(record: Record) -> RetrieverResultItem:
        """Format retrieval result as RetrieverResultItem for LLM context."""
        result = record.get("result") or {}
        score = record.get("score", 0.0)

        output = []
        metadata: dict = {"score": score, "node_type": node_type}

        if node_type == "Example":
            source_file = result.get("source_file", "unknown")
            line = result.get("line", "?")
            source_code = result.get("source_code", "")

            metadata.update(
                {
                    "api_path": f"{source_file}:{line}",
                    "name": result.get("header") or source_file,
                    "example_type": result.get("example_type"),
                    "api_tier": result.get("api_tier") or "example",
                    "content_preview": source_code[:200],
                }
            )

            output.append(f"## Example from {source_file}:{line} (relevance: {score:.3f})")
            if result.get("header"):
                output.append(f"\n**Topic:** {result['header']}")
            output.append(f"\n```python\n{source_code}\n```")
        else:
            api_path = result.get("api_path", "Unknown")
            name = result.get("name", "")
            api_tier = result.get("api_tier") or classify_api_tier(api_path, name, node_type)
            metadata.update(
                {
                    "api_path": api_path,
                    "name": name,
                    "api_tier": api_tier,
                    "content_preview": result.get("description", ""),
                }
            )

            output.append(f"## {api_path} (relevance: {score:.3f})")

            if result.get("description"):
                output.append(f"\n**Description:** {result['description']}")

            if result.get("header"):
                output.append(f"\n**Signature:** `{result['header']}`")

            methods = result.get("methods", [])
            if methods:
                output.append("\n**Methods:**")
                for method in methods[:5]:
                    output.append(f"\n- `{method['api_path']}`: {method.get('description', 'No description')}")

            examples = result.get("examples", [])
            if examples:
                output.append("\n**Usage Examples:**")
                for i, example in enumerate(examples[:3], 1):
                    output.append(
                        f"\n**Example {i}** (from {example.get('source_file', 'unknown')}:{example.get('line', '?')}):"
                    )
                    output.append(f"```python\n{example.get('source_code', '')}\n```")

        content = "\n".join(output)
        return RetrieverResultItem(content=content, metadata=metadata)

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

    Combines results from Class, Function, Method, and Example indexes
    using reciprocal rank fusion.
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
        """Search across all node types and return fused results.

        Args:
            query_text: Query text
            top_k: Number of final results (default: 5)

        Returns:
            List of formatted result strings
        """
        ranked_lists: dict[str, list[RetrieverResultItem]] = {}

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
                ranked_lists[node_type] = list(results.items)
            except Exception as e:
                logger.warning("Search failed for {}: {}", node_type, e)
                ranked_lists[node_type] = []

        return reciprocal_rank_fusion(ranked_lists, top_k=top_k)

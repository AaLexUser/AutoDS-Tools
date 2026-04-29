"""Neo4j graph converter for Python repository data."""

import contextlib
import hashlib
import json
from typing import TYPE_CHECKING, Any

from neo4j import GraphDatabase

if TYPE_CHECKING:
    from pygrad.processor.processor import ClassInfo, FunctionInfo


class Neo4jGraphConverter:
    """Converts repository data to Neo4j knowledge graph."""

    def __init__(self, uri: str, username: str, password: str, database: str = "neo4j"):
        """Initialize Neo4j connection.

        Args:
            uri: Neo4j connection URI (e.g., "bolt://localhost:7687")
            username: Neo4j username
            password: Neo4j password
            database: Database name (default: "neo4j")
        """
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        self.database = database

    def close(self) -> None:
        """Close the Neo4j driver connection."""
        self.driver.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def save_repository_graph(
        self,
        classes: list["ClassInfo"],
        functions: list["FunctionInfo"],
        repository_id: str,
        clear_existing: bool = False,
    ) -> dict[str, int]:
        """Save repository data as Neo4j graph.

        Args:
            classes: List of class information
            functions: List of function information
            repository_id: Repository identifier for node isolation
            clear_existing: Whether to clear existing graph data for this repository

        Returns:
            Dictionary with counts of created nodes and relationships
        """
        with self.driver.session(database=self.database) as session:
            if clear_existing:
                session.run(
                    "MATCH (n {repository_id: $repository_id}) DETACH DELETE n",
                    repository_id=repository_id,
                )

            # Create constraints and indexes
            self._create_constraints(session)

            # Track statistics
            stats = {
                "classes": 0,
                "functions": 0,
                "methods": 0,
                "examples": 0,
                "relationships": 0,
            }

            # Create class nodes and their methods
            for class_info in classes:
                self._create_class_node(session, class_info, repository_id)
                stats["classes"] += 1

                # Create method nodes and relationships
                for method in class_info.methods:
                    self._create_method_node(session, method, class_info.api_path, repository_id)
                    stats["methods"] += 1
                    stats["relationships"] += 1

                # Create class examples
                for example_json in class_info.usage_examples:
                    example_id = self._create_example_node(session, example_json, repository_id)
                    if example_id:
                        self._create_example_relationship(
                            session, class_info.api_path, example_id, "Class", repository_id
                        )
                        stats["relationships"] += 1

                # Create method examples
                for method in class_info.methods:
                    for example_json in method.usage_examples:
                        example_id = self._create_example_node(session, example_json, repository_id)
                        if example_id:
                            self._create_example_relationship(
                                session, method.api_path, example_id, "Method", repository_id
                            )
                            stats["relationships"] += 1

            # Create function nodes
            for func in functions:
                self._create_function_node(session, func, repository_id)
                stats["functions"] += 1

                # Create function examples
                for example_json in func.usage_examples:
                    example_id = self._create_example_node(session, example_json, repository_id)
                    if example_id:
                        self._create_example_relationship(session, func.api_path, example_id, "Function", repository_id)
                        stats["relationships"] += 1

            # Count unique examples for this repository
            result = session.run(
                "MATCH (e:Example {repository_id: $repository_id}) RETURN count(e) as count",
                repository_id=repository_id,
            )
            row = result.single()
            stats["examples"] = row["count"] if row is not None else 0

            return stats

    def _create_constraints(self, session) -> None:
        """Create unique constraints and indexes for repository isolation."""
        # Composite unique constraints: (repository_id, api_path) or (repository_id, id)
        constraints = [
            "CREATE CONSTRAINT class_repo_api_path IF NOT EXISTS FOR (c:Class) REQUIRE (c.repository_id, c.api_path) IS UNIQUE",
            "CREATE CONSTRAINT function_repo_api_path IF NOT EXISTS FOR (f:Function) REQUIRE (f.repository_id, f.api_path) IS UNIQUE",
            "CREATE CONSTRAINT method_repo_api_path IF NOT EXISTS FOR (m:Method) REQUIRE (m.repository_id, m.api_path) IS UNIQUE",
            "CREATE CONSTRAINT example_repo_id IF NOT EXISTS FOR (e:Example) REQUIRE (e.repository_id, e.id) IS UNIQUE",
        ]

        # Indexes on repository_id for performance
        indexes = [
            "CREATE INDEX class_repository_id IF NOT EXISTS FOR (c:Class) ON (c.repository_id)",
            "CREATE INDEX function_repository_id IF NOT EXISTS FOR (f:Function) ON (f.repository_id)",
            "CREATE INDEX method_repository_id IF NOT EXISTS FOR (m:Method) ON (m.repository_id)",
            "CREATE INDEX example_repository_id IF NOT EXISTS FOR (e:Example) ON (e.repository_id)",
        ]

        for constraint in constraints:
            with contextlib.suppress(Exception):
                session.run(constraint)

        for index in indexes:
            with contextlib.suppress(Exception):
                session.run(index)

    def _create_class_node(self, session, class_info: "ClassInfo", repository_id: str) -> None:
        """Create a Class node."""
        query = """
        MERGE (c:Class {repository_id: $repository_id, api_path: $api_path})
        SET c.name = $name,
            c.description = $description,
            c.init_parameters = $init_parameters,
            c.init_description = $init_description
        """
        session.run(
            query,
            repository_id=repository_id,
            api_path=class_info.api_path,
            name=class_info.name,
            description=class_info.description,
            init_parameters=class_info.initialization.get("parameters", ""),
            init_description=class_info.initialization.get("description", ""),
        )

    def _create_function_node(self, session, func: "FunctionInfo", repository_id: str) -> None:
        """Create a Function node."""
        query = """
        MERGE (f:Function {repository_id: $repository_id, api_path: $api_path})
        SET f.name = $name,
            f.description = $description,
            f.header = $header,
            f.output = $output
        """
        session.run(
            query,
            repository_id=repository_id,
            api_path=func.api_path,
            name=func.name,
            description=func.description,
            header=func.header,
            output=func.output,
        )

    def _create_method_node(self, session, method: "FunctionInfo", class_api_path: str, repository_id: str) -> None:
        """Create a Method node and link it to its Class."""
        # Create method node
        query = """
        MERGE (m:Method {repository_id: $repository_id, api_path: $api_path})
        SET m.name = $name,
            m.description = $description,
            m.header = $header,
            m.output = $output
        """
        session.run(
            query,
            repository_id=repository_id,
            api_path=method.api_path,
            name=method.name,
            description=method.description,
            header=method.header,
            output=method.output,
        )

        # Create relationship to class
        relationship_query = """
        MATCH (c:Class {repository_id: $repository_id, api_path: $class_api_path})
        MATCH (m:Method {repository_id: $repository_id, api_path: $method_api_path})
        MERGE (c)-[:CONTAINS]->(m)
        """
        session.run(
            relationship_query,
            repository_id=repository_id,
            class_api_path=class_api_path,
            method_api_path=method.api_path,
        )

    def _create_example_node(self, session, example_json: str, repository_id: str) -> str | None:
        """Create or merge an Example node, returns example ID."""
        try:
            data = json.loads(example_json)
        except (json.JSONDecodeError, TypeError):
            return None

        # Create unique ID for example
        example_id = self._generate_example_id(data)

        query = """
        MERGE (e:Example {repository_id: $repository_id, id: $id})
        SET e.source_file = $source_file,
            e.example_type = $example_type,
            e.line = $line,
            e.variable = $variable,
            e.header = $header,
            e.source_code = $source_code
        """
        session.run(
            query,
            repository_id=repository_id,
            id=example_id,
            source_file=data.get("from", ""),
            example_type=data.get("type", ""),
            line=data.get("line"),
            variable=data.get("variable"),
            header=data.get("header"),
            source_code=data.get("source_code", ""),
        )

        return example_id

    def _create_example_relationship(
        self, session, api_path: str, example_id: str, node_type: str, repository_id: str
    ) -> None:
        """Create HAS_EXAMPLE relationship between entity and example."""
        query = f"""
        MATCH (n:{node_type} {{repository_id: $repository_id, api_path: $api_path}})
        MATCH (e:Example {{repository_id: $repository_id, id: $example_id}})
        MERGE (n)-[:HAS_EXAMPLE]->(e)
        """
        session.run(query, repository_id=repository_id, api_path=api_path, example_id=example_id)

    def _generate_example_id(self, example_data: dict[str, Any]) -> str:
        """Generate unique ID for an example based on its content."""
        # Use source file, line, and source code hash for uniqueness
        source_file = example_data.get("from", "")
        line = str(example_data.get("line", ""))
        source_code = example_data.get("source_code", "")

        # Create hash of source code to handle duplicates
        code_hash = hashlib.md5(source_code.encode()).hexdigest()[:8]

        return f"{source_file}:{line}:{code_hash}"

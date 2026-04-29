"""Tests for Neo4j graph converter."""

import json
from unittest.mock import MagicMock, patch

import pytest

from pygrad.processor.neo4j_graph import Neo4jGraphConverter
from pygrad.processor.processor import ClassInfo, FunctionInfo


@pytest.fixture
def sample_class():
    """Sample ClassInfo for testing."""
    return ClassInfo(
        name="TestClass",
        api_path="module.TestClass",
        description="A test class",
        initialization={"parameters": "self, x, y", "description": "Initialize test class"},
        methods=[
            FunctionInfo(
                name="test_method",
                api_path="module.TestClass.test_method",
                description="A test method",
                header="def test_method(self, arg)",
                output="",
                usage_examples=[
                    json.dumps(
                        {
                            "from": "test.py",
                            "type": "method_call",
                            "line": 10,
                            "variable": "obj",
                            "header": None,
                            "source_code": "obj.test_method(42)",
                        }
                    )
                ],
            )
        ],
        usage_examples=[
            json.dumps(
                {
                    "from": "example.py",
                    "type": "class_instantiation",
                    "line": 5,
                    "variable": "obj",
                    "header": None,
                    "source_code": "obj = TestClass(1, 2)",
                }
            )
        ],
    )


@pytest.fixture
def sample_function():
    """Sample FunctionInfo for testing."""
    return FunctionInfo(
        name="test_function",
        api_path="module.test_function",
        description="A test function",
        header="def test_function(x, y)",
        output="int",
        usage_examples=[
            json.dumps(
                {
                    "from": "example.py",
                    "type": "function_call",
                    "line": 15,
                    "variable": "result",
                    "header": None,
                    "source_code": "result = test_function(1, 2)",
                }
            )
        ],
    )


@patch("pygrad.processor.neo4j_graph.GraphDatabase")
def test_neo4j_converter_initialization(mock_graph_db):
    """Test Neo4j converter initialization."""
    mock_driver = MagicMock()
    mock_graph_db.driver.return_value = mock_driver

    converter = Neo4jGraphConverter("bolt://localhost:7687", "neo4j", "password")

    mock_graph_db.driver.assert_called_once_with("bolt://localhost:7687", auth=("neo4j", "password"))
    assert converter.driver == mock_driver
    assert converter.database == "neo4j"


@patch("pygrad.processor.neo4j_graph.GraphDatabase")
def test_context_manager(mock_graph_db):
    """Test Neo4j converter as context manager."""
    mock_driver = MagicMock()
    mock_graph_db.driver.return_value = mock_driver

    with Neo4jGraphConverter("bolt://localhost:7687", "neo4j", "password") as converter:
        assert converter.driver == mock_driver

    mock_driver.close.assert_called_once()


@patch("pygrad.processor.neo4j_graph.GraphDatabase")
def test_save_repository_graph(mock_graph_db, sample_class, sample_function):
    """Test saving repository graph to Neo4j."""
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.single.return_value = {"count": 2}

    mock_graph_db.driver.return_value = mock_driver
    mock_driver.session.return_value.__enter__.return_value = mock_session
    mock_session.run.return_value = mock_result

    converter = Neo4jGraphConverter("bolt://localhost:7687", "neo4j", "password")
    stats = converter.save_repository_graph(
        classes=[sample_class], functions=[sample_function], repository_id="test-repo", clear_existing=True
    )

    # Verify session was created
    mock_driver.session.assert_called_with(database="neo4j")

    # Verify stats
    assert stats["classes"] == 1
    assert stats["functions"] == 1
    assert stats["methods"] == 1
    assert stats["examples"] == 2
    assert stats["relationships"] > 0


@patch("pygrad.processor.neo4j_graph.GraphDatabase")
def test_example_deduplication(mock_graph_db):
    """Test that duplicate examples are merged."""
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.single.return_value = {"count": 1}  # Only 1 unique example

    mock_graph_db.driver.return_value = mock_driver
    mock_driver.session.return_value.__enter__.return_value = mock_session
    mock_session.run.return_value = mock_result

    # Create two functions with the same example
    same_example = json.dumps(
        {
            "from": "test.py",
            "type": "function_call",
            "line": 10,
            "variable": "x",
            "header": None,
            "source_code": "x = foo()",
        }
    )

    func1 = FunctionInfo(
        name="func1",
        api_path="module.func1",
        description="Function 1",
        header="def func1()",
        output="",
        usage_examples=[same_example],
    )

    func2 = FunctionInfo(
        name="func2",
        api_path="module.func2",
        description="Function 2",
        header="def func2()",
        output="",
        usage_examples=[same_example],
    )

    converter = Neo4jGraphConverter("bolt://localhost:7687", "neo4j", "password")
    stats = converter.save_repository_graph(
        classes=[], functions=[func1, func2], repository_id="test-repo", clear_existing=True
    )

    # Should have 2 functions but only 1 unique example
    assert stats["functions"] == 2
    assert stats["examples"] == 1


def test_generate_example_id():
    """Test example ID generation."""
    converter = Neo4jGraphConverter("bolt://localhost:7687", "neo4j", "password")

    example1 = {
        "from": "test.py",
        "line": 10,
        "source_code": "x = foo()",
    }

    example2 = {
        "from": "test.py",
        "line": 10,
        "source_code": "x = foo()",
    }

    example3 = {
        "from": "test.py",
        "line": 11,
        "source_code": "x = foo()",
    }

    id1 = converter._generate_example_id(example1)
    id2 = converter._generate_example_id(example2)
    id3 = converter._generate_example_id(example3)

    # Same content should generate same ID
    assert id1 == id2

    # Different line should generate different ID
    assert id1 != id3

    # ID should contain file, line, and hash
    assert "test.py" in id1
    assert "10" in id1

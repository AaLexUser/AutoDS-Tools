"""Processor module for generating API documentation."""

from pygrad.processor.example_extractor import (
    APIUsageGroup,
    ExampleExtractor,
    UsageExample,
    extract_examples_from_repository,
)
from pygrad.processor.neo4j_graph import Neo4jGraphConverter
from pygrad.processor.processor import (
    ClassInfo,
    FunctionInfo,
    PythonRepositoryProcessor,
    process_repository,
    process_repository_to_neo4j,
)
from pygrad.processor.utils import extract_important_api, extract_test_example_paths

__all__ = [
    "APIUsageGroup",
    "ClassInfo",
    "ExampleExtractor",
    "FunctionInfo",
    "Neo4jGraphConverter",
    "PythonRepositoryProcessor",
    "UsageExample",
    "extract_examples_from_repository",
    "extract_important_api",
    "extract_test_example_paths",
    "process_repository",
    "process_repository_to_neo4j",
]

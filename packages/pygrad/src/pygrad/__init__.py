"""Pygrad - Graph RAG API Doc library.

Build searchable knowledge graphs from Python repository documentation.

Usage:
    import pygrad as pg

    # Add a repository to the knowledge graph
    await pg.add("https://github.com/owner/repo")

    # List all indexed repositories
    datasets = await pg.list()

    # Search the knowledge graph
    result = await pg.search("https://github.com/owner/repo", "How to use X?")

    # Delete a repository
    await pg.delete("https://github.com/owner/repo")
"""

from pygrad.common.log import setup_logging
from pygrad.config import PYGRAD_HOME, REPO_STORAGE
from pygrad.core import (
    add,
    delete,
    get_dataset,
    list,
    list_datasets,
    search,
    visualize,
)
from pygrad.parser.treesitter import RepoTreeSitter
from pygrad.processor.processor import (
    ClassInfo,
    FunctionInfo,
    PythonRepositoryProcessor,
    process_repository,
)
from pygrad.repository import clone_repository, get_repository_id

setup_logging()

__version__ = "0.0.1"

__all__ = [
    # Configuration
    "PYGRAD_HOME",
    "REPO_STORAGE",
    # Processor
    "ClassInfo",
    "FunctionInfo",
    "PythonRepositoryProcessor",
    # Parser
    "RepoTreeSitter",
    "__version__",
    # Numpy-style API (primary)
    "add",
    # Repository utilities
    "clone_repository",
    "delete",
    "get_dataset",
    "get_repository_id",
    "list",
    "list_datasets",
    "process_repository",
    "search",
    "visualize",
]

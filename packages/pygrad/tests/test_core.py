"""Black-box tests for the public core API."""

from __future__ import annotations

import shutil
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

import pygrad.core as core
from pygrad.graphrag.common import NODE_LABELS
from pygrad.graphrag.config import SearchBackend
from pygrad.repository import get_repository_id

SAMPLE_URL = "https://github.com/example/project"
AsyncCallable = Callable[..., Awaitable[Any]]


class FakeCogneeModule(ModuleType):
    """Typed fake cognee module"""

    datasets: Any
    SearchType: Any
    add: AsyncCallable
    cognify: AsyncCallable
    search: AsyncCallable


class FakeSetupModule(ModuleType):
    """Typed fake setup module"""

    setup: AsyncCallable


class FakeVisualizeModule(ModuleType):
    """Typed fake visualize module"""

    visualize_graph: AsyncCallable


class FakeRunResult:
    """Neo4j result double supporting iteration and single()."""

    def __init__(self, *, rows=None, single_row=None):
        self._rows = rows or []
        self._single_row = single_row

    def __iter__(self):
        return iter(self._rows)

    def single(self):
        return self._single_row


class FakeSession:
    """Neo4j session double that replays prepared run results."""

    def __init__(self, results):
        self._results = list(results)
        self.run_calls = []

    def run(self, query, **params):
        self.run_calls.append((query, params))
        return self._results.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeDriver:
    """Neo4j driver double that returns prepared sessions."""

    def __init__(self, sessions):
        self._sessions = list(sessions)
        self.closed = False
        self.session_databases = []

    def session(self, *, database):
        self.session_databases.append(database)
        return self._sessions.pop(0)

    def close(self):
        self.closed = True


def install_fake_cognee_runtime(monkeypatch, *, datasets=None, search_result=None):
    """Install a fake Cognee runtime into sys.modules."""
    records = SimpleNamespace(
        add_calls=[],
        cognify_calls=[],
        empty_dataset_calls=[],
        search_calls=[],
        setup_calls=[],
        visualize_calls=[],
    )

    async def list_datasets():
        return list(datasets or [])

    async def empty_dataset(dataset_id):
        records.empty_dataset_calls.append(dataset_id)

    async def add(documents, **kwargs):
        records.add_calls.append({"documents": list(documents), **kwargs})

    async def cognify(**kwargs):
        records.cognify_calls.append(kwargs)

    async def search(**kwargs):
        records.search_calls.append(kwargs)
        return search_result if search_result is not None else []

    async def setup():
        records.setup_calls.append("setup")

    async def visualize_graph(path):
        records.visualize_calls.append(path)

    cognee_module = FakeCogneeModule("cognee")
    cognee_module.datasets = SimpleNamespace(
        list_datasets=list_datasets,
        empty_dataset=empty_dataset,
    )
    cognee_module.SearchType = SimpleNamespace(GRAPH_COMPLETION_CONTEXT_EXTENSION="graph-completion-context-extension")
    cognee_module.add = add
    cognee_module.cognify = cognify
    cognee_module.search = search

    setup_module = FakeSetupModule("cognee.modules.engine.operations.setup")
    setup_module.setup = setup

    visualize_module = FakeVisualizeModule("cognee.api.v1.visualize.visualize")
    visualize_module.visualize_graph = visualize_graph

    monkeypatch.setitem(sys.modules, "cognee", cognee_module)
    monkeypatch.setitem(sys.modules, "cognee.modules", ModuleType("cognee.modules"))
    monkeypatch.setitem(sys.modules, "cognee.modules.engine", ModuleType("cognee.modules.engine"))
    monkeypatch.setitem(
        sys.modules,
        "cognee.modules.engine.operations",
        ModuleType("cognee.modules.engine.operations"),
    )
    monkeypatch.setitem(sys.modules, "cognee.modules.engine.operations.setup", setup_module)
    monkeypatch.setitem(sys.modules, "cognee.api", ModuleType("cognee.api"))
    monkeypatch.setitem(sys.modules, "cognee.api.v1", ModuleType("cognee.api.v1"))
    monkeypatch.setitem(sys.modules, "cognee.api.v1.visualize", ModuleType("cognee.api.v1.visualize"))
    monkeypatch.setitem(sys.modules, "cognee.api.v1.visualize.visualize", visualize_module)

    return records


class TestCogneeBackend:
    """Public API behavior when the Cognee backend is active."""

    @pytest.mark.asyncio
    async def test_add_indexes_repository_from_cloned_cache(self, monkeypatch, temp_dir, sample_repo):
        """Adding a repo creates API docs and submits extracted documents to Cognee."""
        repo_id = get_repository_id(SAMPLE_URL)
        storage_dir = temp_dir / "storage"
        monkeypatch.setenv("SEARCH_BACKEND", SearchBackend.COGNEE.value)
        monkeypatch.setattr(core, "REPO_STORAGE", str(storage_dir))
        records = install_fake_cognee_runtime(monkeypatch)

        def fake_clone_repository(url: str, target: Path) -> None:
            assert url == SAMPLE_URL
            shutil.copytree(sample_repo, target)

        monkeypatch.setattr(core, "clone_repository", fake_clone_repository)

        await core.add(SAMPLE_URL)

        assert (storage_dir / repo_id / "api.xml").exists()
        assert records.setup_calls == ["setup"]
        assert len(records.add_calls) == 1
        assert records.add_calls[0]["dataset_name"] == repo_id
        assert records.add_calls[0]["preferred_loaders"] == ["text_loader"]
        assert records.add_calls[0]["documents"]
        assert len(records.cognify_calls) == 1

    @pytest.mark.asyncio
    async def test_search_returns_not_indexed_when_dataset_missing(self, monkeypatch):
        """Searching an unknown repository returns the documented sentinel message."""
        monkeypatch.setenv("SEARCH_BACKEND", SearchBackend.COGNEE.value)
        install_fake_cognee_runtime(monkeypatch, datasets=[])

        result = await core.search(SAMPLE_URL, "How do I use it?")

        assert result == "The library is not yet indexed."

    @pytest.mark.asyncio
    async def test_search_returns_normalized_cognee_result(self, monkeypatch):
        """Search returns normalized text from the external Cognee response."""
        repo_id = get_repository_id(SAMPLE_URL)
        dataset_id = str(uuid4())
        records = install_fake_cognee_runtime(
            monkeypatch,
            datasets=[SimpleNamespace(name=repo_id.upper(), id=dataset_id)],
            search_result=[{"search_result": ["Use helper() to start."]}],
        )
        monkeypatch.setenv("SEARCH_BACKEND", SearchBackend.COGNEE.value)

        result = await core.search(SAMPLE_URL, "How do I start?")

        assert result == "Use helper() to start."
        assert len(records.search_calls) == 1
        assert records.search_calls[0]["query_text"] == "How do I start?"
        assert records.search_calls[0]["dataset_ids"] == [UUID(dataset_id)]

    @pytest.mark.asyncio
    async def test_get_dataset_matches_names_case_insensitively(self, monkeypatch):
        """Dataset lookup ignores repository-name casing."""
        dataset = SimpleNamespace(name="Example-Project", id="dataset-1")
        monkeypatch.setenv("SEARCH_BACKEND", SearchBackend.COGNEE.value)
        install_fake_cognee_runtime(monkeypatch, datasets=[dataset])

        result = await core.get_dataset("example-project")

        assert result is dataset

    @pytest.mark.asyncio
    async def test_get_dataset_returns_default_when_missing(self, monkeypatch):
        """Dataset lookup falls back to the provided default."""
        fallback = object()
        monkeypatch.setenv("SEARCH_BACKEND", SearchBackend.COGNEE.value)
        install_fake_cognee_runtime(monkeypatch, datasets=[])

        result = await core.get_dataset("missing-repo", default=fallback)

        assert result is fallback

    @pytest.mark.asyncio
    async def test_delete_empties_existing_dataset(self, monkeypatch):
        """Deleting an indexed repo empties the matching external dataset."""
        repo_id = get_repository_id(SAMPLE_URL)
        dataset = SimpleNamespace(name=repo_id, id="dataset-123")
        records = install_fake_cognee_runtime(monkeypatch, datasets=[dataset])
        monkeypatch.setenv("SEARCH_BACKEND", SearchBackend.COGNEE.value)

        await core.delete(SAMPLE_URL)

        assert records.empty_dataset_calls == ["dataset-123"]

    @pytest.mark.asyncio
    async def test_visualize_returns_requested_output_path(self, monkeypatch, temp_dir):
        """Visualization returns the same destination path after export."""
        output_path = temp_dir / "graph.html"
        records = install_fake_cognee_runtime(monkeypatch)

        result = await core.visualize(str(output_path))

        assert result == str(output_path)
        assert records.setup_calls == ["setup"]
        assert records.visualize_calls == [str(output_path)]


class TestNeo4jBackend:
    """Public API behavior when the Neo4j GraphRAG backend is active."""

    @pytest.fixture(autouse=True)
    def neo4j_env(self, monkeypatch):
        monkeypatch.setenv("SEARCH_BACKEND", SearchBackend.NEO4J_GRAPHRAG.value)
        monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
        monkeypatch.setenv("NEO4J_USERNAME", "neo4j")
        monkeypatch.setenv("NEO4J_PASSWORD", "password")
        monkeypatch.setenv("NEO4J_DATABASE", "pygrad")

    @pytest.mark.asyncio
    async def test_list_datasets_returns_repository_ids(self, monkeypatch):
        """Listing datasets exposes Neo4j repository ids as dataset-like objects."""
        rows = [
            {"repository_id": "example-another"},
            {"repository_id": "example-project"},
        ]
        session = FakeSession([FakeRunResult(rows=rows)])
        driver = FakeDriver([session])
        monkeypatch.setattr(core.GraphDatabase, "driver", lambda uri, auth: driver)

        datasets = await core.list_datasets()

        assert [(dataset.name, dataset.id) for dataset in datasets] == [
            ("example-another", "example-another"),
            ("example-project", "example-project"),
        ]
        assert driver.session_databases == ["pygrad"]
        assert driver.closed is True

    @pytest.mark.asyncio
    async def test_search_returns_not_indexed_when_repository_has_no_nodes(self, monkeypatch):
        """Searching a repo with no graph nodes returns the sentinel message."""
        session = FakeSession([FakeRunResult(single_row={"count": 0})])
        driver = FakeDriver([session])
        monkeypatch.setattr(core.GraphDatabase, "driver", lambda uri, auth: driver)

        result = await core.search(SAMPLE_URL, "How do I start?")

        assert result == "The library is not yet indexed."
        assert driver.closed is True

    @pytest.mark.asyncio
    async def test_delete_removes_repository_nodes_and_indexes(self, monkeypatch):
        """Deleting a repo removes its nodes and drops all repository vector indexes."""
        repo_id = get_repository_id(SAMPLE_URL)
        results = [FakeRunResult()] * (1 + len(NODE_LABELS))
        session = FakeSession(results)
        driver = FakeDriver([session])
        monkeypatch.setattr(core.GraphDatabase, "driver", lambda uri, auth: driver)

        await core.delete(SAMPLE_URL)

        delete_query, delete_params = session.run_calls[0]
        assert "DETACH DELETE n" in delete_query
        assert delete_params == {"repo_id": repo_id}

        drop_queries = [query for query, _ in session.run_calls[1:]]
        assert drop_queries == [f"DROP INDEX `{repo_id}_{node_type}_embeddings` IF EXISTS" for node_type in NODE_LABELS]
        assert driver.closed is True

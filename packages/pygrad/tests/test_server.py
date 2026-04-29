"""Tests for the FastAPI REST server."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from pygrad.server import app

SAMPLE_URL = "https://github.com/owner/repo"


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


class TestAddRepo:
    """Tests for POST /repos — index a repository."""

    def test_returns_202_and_schedules_indexing(self, client):
        """202 is returned immediately; pg.add is dispatched as a background task."""
        mock_add = AsyncMock()
        with patch("pygrad.server.pg.add", mock_add):
            response = client.post("/repos", json={"url": SAMPLE_URL})

        assert response.status_code == 202
        assert response.json() == {"message": "Indexing started", "url": SAMPLE_URL}
        mock_add.assert_awaited_once_with(SAMPLE_URL)

    def test_missing_url_returns_422(self, client):
        """Request body without url is rejected by schema validation."""
        response = client.post("/repos", json={})
        assert response.status_code == 422


class TestListRepos:
    """Tests for GET /repos — list indexed repositories."""

    def test_returns_indexed_repos(self, client):
        """Each dataset name is surfaced in the response list."""
        datasets = [SimpleNamespace(name="owner-repo"), SimpleNamespace(name="other-repo")]
        with patch("pygrad.server.pg.list", AsyncMock(return_value=datasets)):
            response = client.get("/repos")

        assert response.status_code == 200
        assert response.json() == [{"name": "owner-repo"}, {"name": "other-repo"}]

    def test_empty_list_when_nothing_indexed(self, client):
        """Empty knowledge graph returns an empty JSON array."""
        with patch("pygrad.server.pg.list", AsyncMock(return_value=[])):
            response = client.get("/repos")

        assert response.json() == []


class TestSearchRepo:
    """Tests for POST /repos/search — query a knowledge graph."""

    def test_returns_search_result(self, client):
        """Successful search result is forwarded in the response body."""
        with patch("pygrad.server.pg.search", AsyncMock(return_value="Use requests.get()")):
            response = client.post(
                "/repos/search",
                json={"url": SAMPLE_URL, "query": "How to GET?"},
            )

        assert response.status_code == 200
        assert response.json() == {"result": "Use requests.get()"}

    def test_not_yet_indexed_message_is_forwarded(self, client):
        """pg.search returns a sentinel string when the repo is missing — server forwards it as-is."""
        with patch("pygrad.server.pg.search", AsyncMock(return_value="The library is not yet indexed.")):
            response = client.post(
                "/repos/search",
                json={"url": SAMPLE_URL, "query": "anything"},
            )

        assert response.json() == {"result": "The library is not yet indexed."}

    def test_missing_query_returns_422(self, client):
        """Request body without query field is rejected."""
        response = client.post("/repos/search", json={"url": SAMPLE_URL})
        assert response.status_code == 422


class TestDeleteRepo:
    """Tests for DELETE /repos — remove a repository."""

    def test_returns_deleted_message(self, client):
        """pg.delete is called with the URL from the query parameter."""
        mock_delete = AsyncMock()
        with patch("pygrad.server.pg.delete", mock_delete):
            response = client.delete("/repos", params={"url": SAMPLE_URL})

        assert response.status_code == 200
        assert response.json() == {"message": "Deleted", "url": SAMPLE_URL}
        mock_delete.assert_awaited_once_with(SAMPLE_URL)

    def test_missing_url_returns_422(self, client):
        """DELETE without the required url query param is rejected."""
        response = client.delete("/repos")
        assert response.status_code == 422


class TestVisualize:
    """Tests for GET /visualize — knowledge-graph HTML export."""

    def test_returns_html_content(self, client):
        """pg.visualize writes to the temp path; endpoint reads it back and streams HTML."""

        async def _write(path: str) -> str:
            with open(path, "w") as f:
                f.write("<html><body>graph</body></html>")
            return path

        with patch("pygrad.server.pg.visualize", AsyncMock(side_effect=_write)):
            response = client.get("/visualize")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "graph" in response.text

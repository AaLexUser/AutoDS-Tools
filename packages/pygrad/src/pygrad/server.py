"""FastAPI REST server for PyGrad.

Run with:
    uvicorn pygrad.server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os
import tempfile

from fastapi import BackgroundTasks, FastAPI, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import pygrad as pg
from pygrad.common.log import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title="PyGrad",
    description="REST API for PyGrad - search knowledge graphs built from Python repositories.",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RepoURL(BaseModel):
    url: str


class SearchRequest(BaseModel):
    url: str
    query: str


class RepoInfo(BaseModel):
    name: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/repos", status_code=202)
async def add_repo(body: RepoURL, background_tasks: BackgroundTasks) -> dict:
    """Index a GitHub repository into the knowledge graph.

    Indexing runs in the background (clone + parse + cognify can take a while).
    The response is returned immediately with **202 Accepted**.
    """
    background_tasks.add_task(_index_repo, body.url)
    return {"message": "Indexing started", "url": body.url}


@app.get("/repos")
async def list_repos() -> list[RepoInfo]:
    """List every repository that has been indexed."""
    datasets = await pg.list()
    return [RepoInfo(name=ds.name) for ds in datasets]


@app.post("/repos/search")
async def search_repo(body: SearchRequest) -> dict:
    """Query an indexed repository's knowledge graph with a natural-language question."""
    result = await pg.search(body.url, body.query)
    return {"result": result}


@app.delete("/repos")
async def delete_repo(url: str = Query(..., description="GitHub repository URL")) -> dict:
    """Remove a repository from the knowledge graph (cached clone is kept on disk)."""
    await pg.delete(url)
    return {"message": "Deleted", "url": url}


@app.get("/visualize", response_class=HTMLResponse)
async def visualize() -> HTMLResponse:
    """Render the full knowledge graph as an interactive HTML page."""
    fd, tmp_path = tempfile.mkstemp(suffix=".html")
    os.close(fd)
    try:
        await pg.visualize(tmp_path)
        with open(tmp_path) as f:
            html = f.read()
    finally:
        os.unlink(tmp_path)
    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# Background helpers
# ---------------------------------------------------------------------------


async def _index_repo(url: str) -> None:
    try:
        await pg.add(url)
    except Exception:
        logger.exception("Failed to index {}", url)

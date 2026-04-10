from __future__ import annotations

import pygrad as pg

from autods.prompting.prompt_store import prompt_store
from autods.tools.base import BaseTool, ToolError


class LibQTool(BaseTool):
    name: str = "libq"

    def get_prompt(self) -> str:
        return prompt_store.load("tools/libq.md")

    async def execute(self, **kwargs) -> str:
        url = kwargs.get("url")
        query = kwargs.get("query")
        if not isinstance(url, str) or not url.strip():
            raise ToolError(
                "Parameter 'url' is required and must be a non-empty string."
            )
        if not isinstance(query, str) or not query.strip():
            raise ToolError(
                "Parameter 'query' is required and must be a non-empty string."
            )
        return await pg.search(url, query)

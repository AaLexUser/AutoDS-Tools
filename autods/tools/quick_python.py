"""QuickPython v2 tool for running lightweight python snippets."""

from __future__ import annotations

import shlex

from langchain_core.messages import HumanMessage

from autods.prompting.prompt_store import prompt_store
from autods.tools.base import BaseTool, ToolError
from autods.tools.shell import ShellTool


class QuickPythonTool(BaseTool):
    """Run inline Python snippets via ``python3 -c`` inside the sandbox."""

    name: str = "py"

    def get_prompt(self) -> str:
        return prompt_store.load("tools/py.md")

    async def execute(self, **kwargs) -> str | HumanMessage:
        code = kwargs.get("code") or kwargs.get("arg")
        if not isinstance(code, str) or not code.strip():
            raise ToolError(
                "Parameter 'code' is required and must be a non-empty string."
            )

        snippet = code.strip()
        command = f"python3 -c {shlex.quote(snippet)}"

        shell_tool = ShellTool()
        return await shell_tool.execute(arg=command)

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from langchain_core.messages import HumanMessage
from langgraph.runtime import get_runtime

from autods.prompting.prompt_store import prompt_store
from autods.tools.base import BaseTool, ToolError
from autods.tools.ipython import IPythonTool
from autods.tools.shell import ShellTool
from autods.utils.parsers import parse_json

Lang = Literal["python", "bash"]


@dataclass
class CodeBlock:
    index: int
    lang: Lang
    code: str


def _collect_human_text(msg: HumanMessage) -> str:
    """Extract a text representation from a HumanMessage (handles LC content lists)."""
    content = getattr(msg, "content", "")
    if isinstance(content, str):
        return content
    # content may be a list of {type: "text"|"image_url", ...}
    parts = [
        str(item.get("text", "")) for item in (content or []) if isinstance(item, dict) and item.get("type") == "text"
    ]
    return "\n".join(p for p in parts if p)


def _get_base_cwd() -> Path:
    """Get project path from runtime context."""
    runtime = get_runtime()
    context = getattr(runtime, "context", None)
    return Path(getattr(context, "project_path", Path.cwd())) if context else Path.cwd()


async def _execute_python_block(blk: CodeBlock, base_cwd: Path, timeout: float | None = None) -> str:
    """Execute a Python code block (file operation or IPython execution)."""

    # Normal IPython execution
    ipy = IPythonTool(timeout=timeout)
    header = f">>> [{blk.lang} #{blk.index}]"
    msg = await ipy.execute(arg=blk.code)
    text = _collect_human_text(msg)
    return f"{header}\n{text}".rstrip()


async def _execute_bash_block(blk: CodeBlock, timeout: float | None = None) -> tuple[str, int]:
    """Execute a bash code block and return (output, exit_code)."""
    code = (blk.code or "").strip()
    if not code:
        return "", 0

    sh = ShellTool(timeout=timeout)
    header = f">>> [{blk.lang} #{blk.index}]"

    raw = await sh.execute(arg=code)

    # Handle both str and HumanMessage return types
    raw_str = raw if isinstance(raw, str) else _collect_human_text(raw)

    try:
        payload = parse_json(raw_str) or {}
        output = str(payload.get("output", "")).rstrip()
        meta = payload.get("metadata", {}) or {}
        exit_code = int(meta.get("exit_code", 0))
        return f"{header}\n{output}".rstrip(), exit_code
    except Exception:
        # Keep raw string if parsing fails unexpectedly
        return f"{header}\n{raw_str}", 1


async def run_block(blk: CodeBlock, timeout: float | None = None) -> tuple[str, int]:
    """Execute block"""

    base_cwd = _get_base_cwd()
    status = 0
    try:
        if blk.lang == "python":
            return await _execute_python_block(blk, base_cwd, timeout), status
        else:  # bash
            return await _execute_bash_block(blk, timeout)
    except Exception as e:
        status = 1
        header = f">>> [{blk.lang} #{blk.index}]"
        return f"{header}\nERROR: {e}", status


class CodeBlocksTool(BaseTool):
    name: str = "CodeBlock"
    usage: str = '<CodeBlock lang="python">print("Hello, World!")</CodeBlock>'
    timeout: float | None = None

    def get_prompt(self) -> str:
        return prompt_store.load("tools/codeblocks.md")

    async def execute(self, **kwargs) -> str | HumanMessage:
        lang = kwargs.get("lang")
        code = kwargs.get("code") or kwargs.get("arg")

        if lang and code:
            block = CodeBlock(index=1, lang=lang, code=code)
        else:
            raise ToolError(f"Not correct usage. Expected: {self.usage}")

        # Ensure runtime context exists for downstream tools
        result, status = await run_block(block, self.timeout)
        if status != 0:
            raise ToolError(result or "Execution failed.")
        return result

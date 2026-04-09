from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

from langchain_core.messages import HumanMessage
from langgraph.runtime import get_runtime

from autods.prompting.prompt_store import prompt_store
from autods.tools._lark_codeblocks import parse_fenced_blocks
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
    file: str | None = None


def parse_code_blocks(text: str) -> list[CodeBlock]:
    pairs = parse_fenced_blocks(text or "")
    return [
        CodeBlock(index=i, lang=lang, code=code)
        for i, (lang, code) in enumerate(pairs, start=1)
    ]


def _collect_human_text(msg: HumanMessage) -> str:
    """Extract a text representation from a HumanMessage (handles LC content lists)."""
    content = getattr(msg, "content", "")
    if isinstance(content, str):
        return content
    # content may be a list of {type: "text"|"image_url", ...}
    parts = [
        str(item.get("text", ""))
        for item in (content or [])
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    return "\n".join(p for p in parts if p)


def _get_base_cwd() -> Path:
    """Get project path from runtime context."""
    runtime = get_runtime()
    context = getattr(runtime, "context", None)
    return Path(getattr(context, "project_path", Path.cwd())) if context else Path.cwd()


async def _execute_python_block(
    blk: CodeBlock, base_cwd: Path, timeout: float | None = None
) -> str:
    """Execute a Python code block (file operation or IPython execution)."""

    # Normal IPython execution
    ipy = IPythonTool(timeout=timeout)
    header = f">>> [{blk.lang} #{blk.index}]"
    msg = await ipy.execute(arg=blk.code)
    text = _collect_human_text(msg)
    return f"{header}\n{text}".rstrip()


async def _execute_bash_block(
    blk: CodeBlock, timeout: float | None = None
) -> tuple[str, int]:
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


async def run_blocks(
    blocks: Sequence[CodeBlock], timeout: float | None = None
) -> tuple[str, int]:
    """Execute blocks sequentially via v2 tools.

    Returns: (aggregated_output, last_status)
      - last_status: 0 for success; non-zero on first error encountered.
    Always stops on first error as requested.
    """
    if not blocks:
        raise ToolError("No supported code blocks found.")

    base_cwd = _get_base_cwd()
    output_parts: list[str] = []
    status = 0

    for blk in blocks:
        try:
            if blk.lang == "python":
                result = await _execute_python_block(blk, base_cwd, timeout)
                output_parts.append(result)
            else:  # bash
                result, exit_code = await _execute_bash_block(blk, timeout)
                output_parts.append(result)
                if exit_code != 0:
                    status = exit_code
                    break
        except Exception as e:
            status = 1
            header = f">>> [{blk.lang} #{blk.index}]"
            output_parts.append(f"{header}\nERROR: {e}")
            break

    return "\n\n".join(output_parts).rstrip(), status


async def run_message(text: str, timeout: float | None = None) -> str:
    blocks = parse_code_blocks(text)
    aggregated, _status = await run_blocks(blocks, timeout)
    return aggregated


class CodeBlocksTool(BaseTool):
    name: str = "CodeBlock"
    usage: str = '<CodeBlock lang="python">print("Hello, World!")</CodeBlock>'
    timeout: float | None = None
    python_executor: Literal["jupyter", "bash"] = "jupyter"

    def get_prompt(self) -> str:
        return prompt_store.load("tools/codeblocks.md")

    async def execute(self, **kwargs) -> str | HumanMessage:
        text = kwargs.get("arg")
        lang = kwargs.get("lang")
        code = kwargs.get("code")
        file = kwargs.get("file")

        if lang and code:
            blocks = [CodeBlock(index=1, lang=lang, code=code, file=file)]
        elif lang and text:
            blocks = [CodeBlock(index=1, lang=lang, code=text, file=file)]
        elif isinstance(text, str) and text.strip():
            blocks = parse_code_blocks(text)
            if len(blocks) > 2:
                raise ToolError(
                    "Only two code blocks are allowed per execution. "
                    "Split your work and run at most two blocks step by step."
                )
        else:
            raise ToolError(f"Not correct usage. Got: {text}, expected: {self.usage}")

        # Ensure runtime context exists for downstream tools
        runtime = get_runtime()
        if getattr(runtime, "context", None) is None:
            raise ToolError("No runtime context available for tool execution.")

        aggregated, status = await run_blocks(blocks, timeout=self.timeout)
        if status != 0:
            # Surface as error to follow the repository's tool error pattern
            raise ToolError(aggregated or "Execution failed.")
        return aggregated

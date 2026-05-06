from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Iterable

from langchain.tools import tool

import pygrad as pg
from autods.environments.jupyter import JupyterExecutor
from autods.environments.sandbox import LocalSandboxAdapter, SandboxResult

MODEL_FORMAT_MAX_BYTES = 10 * 1024
MODEL_FORMAT_MAX_LINES = 256
MODEL_FORMAT_HEAD_LINES = MODEL_FORMAT_MAX_LINES // 2
MODEL_FORMAT_TAIL_LINES = MODEL_FORMAT_MAX_LINES - MODEL_FORMAT_HEAD_LINES
MODEL_FORMAT_HEAD_BYTES = MODEL_FORMAT_MAX_BYTES // 2


def _split_preserving_newlines(content: str) -> Iterable[str]:
    cursor = 0
    while cursor < len(content):
        next_newline = content.find("\n", cursor)
        if next_newline == -1:
            yield content[cursor:]
            break
        yield content[cursor : next_newline + 1]
        cursor = next_newline + 1


def _format_streams(stdout: str, stderr: str) -> str:
    stdout = stdout.rstrip("\n")
    stderr = stderr.rstrip("\n")
    if stdout and stderr:
        return f"{stdout}\n[stderr]\n{stderr}"
    if stderr:
        return f"[stderr]\n{stderr}"
    return stdout


def _truncate_output(content: str) -> str:
    segments = list(_split_preserving_newlines(content))
    total_lines = len(segments)
    if len(content) <= MODEL_FORMAT_MAX_BYTES and total_lines <= MODEL_FORMAT_MAX_LINES:
        return content

    head_take = min(MODEL_FORMAT_HEAD_LINES, total_lines)
    tail_take = MODEL_FORMAT_TAIL_LINES
    omitted = max(total_lines - (head_take + tail_take), 0)

    head = "".join(segments[:head_take])[:MODEL_FORMAT_HEAD_BYTES]
    marker = f"\n[... omitted {omitted} of {total_lines} lines ...]\n\n"
    remaining = max(MODEL_FORMAT_MAX_BYTES - len(head) - len(marker), 0)
    tail = "".join(segments[total_lines - tail_take :])[-remaining:] if remaining else ""

    return f"Total output lines: {total_lines}\n\n{head}{marker}{tail}".rstrip()


def _format_exec_output(result: SandboxResult) -> str:
    combined = _format_streams(result.stdout, result.stderr)
    if result.timed_out:
        combined = f"command timed out after {result.duration_seconds:.1f} seconds\n{combined}".strip()
    return _truncate_output(combined)


def _format_python_output(message: str, image_count: int) -> str:
    parts: list[str] = []
    stripped = message.strip()
    if stripped:
        parts.append(stripped)
    if image_count:
        suffix = "s" if image_count != 1 else ""
        parts.append(f"[image output omitted: {image_count} image{suffix}]")
    return "\n".join(parts).strip() or "Notebook cell executed with no output."


def create_run_shell_tool(
    *,
    sandbox: LocalSandboxAdapter,
    project_path: Path,
    timeout: float | None = None,
):
    @tool("run_shell")
    async def run_shell(command: str) -> str:
        """Run a shell command inside the project workspace."""
        result = await sandbox.run(
            ["bash", "-lc", command],
            cwd=project_path,
            timeout=timeout,
        )
        formatted = _format_exec_output(result)
        if result.exit_code != 0:
            raise RuntimeError(formatted)
        return formatted

    return run_shell


def create_run_python_tool(
    *,
    executor: JupyterExecutor,
    timeout: float | None = None,
):
    @tool("run_python")
    async def run_python(code: str) -> str:
        """Execute Python code in the shared notebook workspace."""
        observation = await executor.run(code=code, timeout=timeout)
        if not observation.is_success:
            raise RuntimeError(observation.message or "Python execution failed.")
        return _format_python_output(observation.message, len(observation.base64_images or []))

    return run_python


def create_libq_search_tool():
    @tool("libq_search")
    async def libq_search(github_url: str, query: str) -> str:
        """Search library documentation and examples with libq."""
        return await pg.search(github_url, query)

    return libq_search


def create_submit_report_tool(
    *,
    report_path: Path,
    on_submit: Callable[[str], None] | None = None,
):
    @tool("submit_report")
    def submit_report(text: str) -> str:
        """Write the stage report to the stage-specific report file."""
        report_path.parent.mkdir(parents=True, exist_ok=True)
        normalized = text.strip()
        report_path.write_text(normalized, encoding="utf-8")
        if on_submit is not None:
            on_submit(normalized)
        return f"Saved report to {report_path}"

    return submit_report

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Iterable

from langchain.tools import tool

import pygrad as pg
from autods.environments.sandbox import LocalSandboxAdapter, SandboxResult, describe_exit_code

MODEL_FORMAT_MAX_BYTES = 10 * 1024
MODEL_FORMAT_MAX_LINES = 256
MODEL_FORMAT_HEAD_LINES = MODEL_FORMAT_MAX_LINES // 2
MODEL_FORMAT_TAIL_LINES = MODEL_FORMAT_MAX_LINES - MODEL_FORMAT_HEAD_LINES
MODEL_FORMAT_HEAD_BYTES = MODEL_FORMAT_MAX_BYTES // 2
TEXT_READ_MAX_BYTES = 2 * 1024 * 1024


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
    exit_summary = describe_exit_code(result.exit_code, timed_out=result.timed_out)
    if exit_summary:
        combined = f"{exit_summary}\n{combined}".strip() if combined else exit_summary
    elif result.timed_out:
        combined = f"command timed out after {result.duration_seconds:.1f} seconds\n{combined}".strip()
    return _truncate_output(combined)


_RUN_PYTHON_PREAMBLE = "import faulthandler\nfaulthandler.enable()\n"


def _workspace_root(project_path: Path) -> Path:
    return project_path.expanduser().resolve()


def _resolve_workspace_path(project_path: Path, user_path: str) -> Path:
    if user_path.strip() == "":
        raise ValueError("path must not be empty")

    path = Path(user_path)
    if path.is_absolute():
        raise ValueError("absolute paths are not allowed")

    root = _workspace_root(project_path)
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("path must stay inside the project workspace") from exc
    return resolved


def _read_text_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"file does not exist: {path}")
    if not path.is_file():
        raise IsADirectoryError(f"path is not a file: {path}")
    if path.stat().st_size > TEXT_READ_MAX_BYTES:
        raise ValueError(f"file is too large to read directly.: {path}")
    return path.read_text(encoding="utf-8", errors="replace")


def _format_lines(content: str, offset: int | None, limit: int | None) -> str:
    if offset is None and limit is None:
        return _truncate_output(content)
    if offset is not None and offset < 1:
        raise ValueError("offset must be >= 1")
    if limit is not None and limit < 1:
        raise ValueError("limit must be >= 1")

    lines = content.splitlines(keepends=True)
    start = 0 if offset is None else offset - 1
    end = None if limit is None else start + limit
    selected = "".join(lines[start:end])
    selected_line_count = len(selected.splitlines())
    last_line = start + selected_line_count if selected_line_count else start
    header = f"Showing lines {start + 1}-{min(len(lines), last_line)} of {len(lines)}"
    if not selected:
        return f"{header}\n"
    return _truncate_output(f"{header}\n\n{selected}")


def create_read_tool(*, project_path: Path):
    @tool("read")
    def read(path: str, offset: int | None = None, limit: int | None = None) -> str:
        """Read a UTF-8 text file inside the project workspace, optionally with 1-indexed line offset/limit."""
        try:
            resolved = _resolve_workspace_path(project_path, path)
            return _format_lines(_read_text_file(resolved), offset, limit)
        except Exception as e:
            return str(e)

    return read

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
    sandbox: LocalSandboxAdapter,
    project_path: Path,
    timeout: float | None = None,
):
    @tool("run_python")
    async def run_python(code: str) -> str:
        """Execute Python code in the project workspace."""
        normalized_code = code if code.endswith("\n") else f"{code}\n"
        result = await sandbox.run(
            ["python", "-u", "-"],
            cwd=project_path,
            timeout=timeout,
            input=f"{_RUN_PYTHON_PREAMBLE}{normalized_code}",
        )
        formatted = _format_exec_output(result)
        if result.exit_code != 0:
            raise RuntimeError(formatted)
        return formatted

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

def create_submit_solution_tool(
    *,
    solution_path: Path,
):
    @tool("submit_solution")
    def submit_solution(code: str) -> str:
        """Submit the final Python code solution for this stage."""
        solution_path.parent.mkdir(parents=True, exist_ok=True)
        solution_path.write_text(code.strip(), encoding="utf-8")
        return f"Saved code to {solution_path}"

    return submit_solution
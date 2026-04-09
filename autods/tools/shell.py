import json
from typing import Iterable

from langchain_core.messages import HumanMessage
from langgraph.runtime import get_runtime

from autods.environments.sandbox import SandboxResult
from autods.prompting.prompt_store import prompt_store
from autods.tools.base import BaseTool, ToolError

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


def _truncate(content: str) -> str:
    segments = list(_split_preserving_newlines(content))
    total_lines = len(segments)
    if len(content) <= MODEL_FORMAT_MAX_BYTES and total_lines <= MODEL_FORMAT_MAX_LINES:
        return content

    head_take = min(MODEL_FORMAT_HEAD_LINES, total_lines)
    tail_take = min(MODEL_FORMAT_TAIL_LINES, max(total_lines - head_take, 0))
    omitted = max(total_lines - (head_take + tail_take), 0)

    head = "".join(segments[:head_take])[:MODEL_FORMAT_HEAD_BYTES]
    marker = f"\n[... omitted {omitted} of {total_lines} lines ...]\n\n"
    remaining = max(MODEL_FORMAT_MAX_BYTES - len(head) - len(marker), 0)
    tail = (
        "".join(segments[total_lines - tail_take :])[-remaining:] if remaining else ""
    )

    formatted = f"Total output lines: {total_lines}\n\n{head}{marker}{tail}".rstrip()
    return formatted


def format_exec_output(result: SandboxResult) -> str:
    combined = _format_streams(result.stdout, result.stderr)
    if result.timed_out:
        combined = f"command timed out after {result.duration_seconds:.1f} seconds\n{combined}".strip()
    payload = {
        "output": _truncate(combined),
        "metadata": {
            "exit_code": result.exit_code,
            "duration_seconds": round(result.duration_seconds, 1),
            "timed_out": result.timed_out,
        },
    }
    return json.dumps(payload, ensure_ascii=False)


class ShellTool(BaseTool):
    name: str = "shell"
    timeout: float | None = None

    def get_prompt(self) -> str:
        return prompt_store.load("tools/shell.md")

    async def execute(self, **kwargs) -> str | HumanMessage:
        command = kwargs.get("arg")
        if not isinstance(command, str) or not command.strip():
            raise ToolError("Command is required and must be a non-empty string.")

        runtime = get_runtime()
        context = getattr(runtime, "context", None)
        if context is None:
            raise ToolError("No runtime context available")

        # Execute all commands via bash -lc to support multi-line scripts and complex shell syntax
        command_args = ["bash", "-lc", command]

        sandbox = context.sandbox
        sandbox_result = await sandbox.run(
            command_args,
            cwd=context.project_path,
            timeout=self.timeout,
        )
        return format_exec_output(sandbox_result)

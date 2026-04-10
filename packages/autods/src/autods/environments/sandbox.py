"""
Local sandbox adapter used for development and testing.

This adapter runs commands directly on the host machine. It does **not**
enforce any isolation beyond forwarding the requested working directory and
environment variables. Production adapters will extend this module to wire in
Seatbelt/seccomp policies while preserving the same async interface.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class SandboxError(RuntimeError):
    """Raised when the sandbox fails before producing a result."""


@dataclass(slots=True)
class SandboxResult:
    """Outcome of executing a command inside the sandbox."""

    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False


class SandboxAdapter(Protocol):
    """Protocol implemented by platform-specific sandbox adapters."""

    async def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
        with_escalated_permissions: bool = False,
    ) -> SandboxResult:
        """
        Execute `command` inside the sandbox returning a `SandboxResult`.

        Implementations must enforce filesystem/network restrictions based on
        the selected sandbox policy (provided indirectly via the adapter
        configuration). The return value should include decoded stdout/stderr,
        even if the command fails.
        """
        ...

    def update_environment(
        self,
        *,
        sandbox_policy: object | None = None,
        workspace: Path | None = None,
        extra_env: MutableMapping[str, str] | None = None,
    ) -> None:
        """
        Optional hook to update the sandbox environment prior to execution.

        The default implementation is a no-op. Concrete adapters can override
        this to stage writable roots, rotate temp directories, or prime cached
        seatbelt/CodeJail policies.
        """
        # no-op default implementation
        return None


class LocalSandboxAdapter(SandboxAdapter):
    """Simple sandbox adapter that delegates to the host operating system."""

    def __init__(self) -> None:
        self._base_env: dict[str, str] = dict(os.environ)

    def update_environment(
        self,
        *,
        sandbox_policy: object | None = None,
        workspace: Path | None = None,
        extra_env: Mapping[str, str] | None = None,
    ) -> None:
        if extra_env:
            self._base_env.update(extra_env)

    async def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
        with_escalated_permissions: bool = False,
    ) -> SandboxResult:
        if not command:
            raise SandboxError("sandbox run requires at least one command argument")

        cmd_env = dict(self._base_env)
        if env:
            cmd_env.update(env)

        start = time.perf_counter()
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
                env=cmd_env,
            )
        except FileNotFoundError as exc:
            raise SandboxError(f"failed to spawn command {command[0]!r}") from exc

        timed_out = False
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except TimeoutError:
            timed_out = True
            process.kill()
            stdout_bytes, stderr_bytes = await process.communicate()

        duration = time.perf_counter() - start

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        exit_code = process.returncode if process.returncode is not None else -1

        if timed_out and exit_code == -1:
            exit_code = 124  # mirror GNU timeout default for clarity

        return SandboxResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            duration_seconds=duration,
        )

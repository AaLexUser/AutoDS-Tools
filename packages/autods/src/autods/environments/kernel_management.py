"""Kernel management module for Jupyter executor.

This module contains classes for managing Jupyter kernel lifecycle,
including kernel specification building and kernel manager functionality.
"""

import asyncio
import inspect
import logging
import os
from pathlib import Path
from typing import Any, Optional

from nbclient.client import KernelClient, KernelManager

logger = logging.getLogger(__name__)


class KernelManagement:
    """Manages Jupyter kernel lifecycle and communication."""

    def __init__(self, env_vars: dict[str, str] | None = None):
        self.km: Optional[KernelManager] = None
        self.kc: Optional[KernelClient] = None
        self._env_vars = env_vars
        self.workspace: Optional[Path] = None

    async def init(self, workspace: Path) -> None:
        """Initialize kernel manager."""
        self.workspace = workspace

        if self.km is not None and self.kc is not None:
            return

        logger.debug("Creating new kernel manager and client")
        from jupyter_client.manager import KernelManager

        self.km = KernelManager(kernel_name="python3")

        kspec = self._build_kernel_spec()
        if kspec is not None:
            setattr(self.km, "_kernel_spec", kspec)

        start_kwargs: dict[str, Any] = {"cwd": str(workspace)}
        if self._env_vars is not None:
            start_kwargs["env"] = dict(self._env_vars)

        self.km.start_kernel(**start_kwargs)

        # Create and start kernel client
        self.kc = self.km.client()
        self.kc.start_channels()
        self.kc.wait_for_ready()

        if hasattr(self.km, "kernel_id"):
            logger.debug(f"Kernel started with ID: {self.km.kernel_id}")

    def _build_kernel_spec(self):
        if not self._env_vars or "VIRTUAL_ENV" not in self._env_vars:
            return None
        from jupyter_client.kernelspec import KernelSpec

        venv_dir = Path(self._env_vars["VIRTUAL_ENV"])
        python = str(
            venv_dir
            / ("Scripts" if os.name == "nt" else "bin")
            / ("python.exe" if os.name == "nt" else "python")
        )
        return KernelSpec(
            argv=[python, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
            display_name="Python (AutoDS)",
            language="python",
            env={},
            resource_dir="",
        )

    async def terminate(self) -> None:
        """Terminate the running kernel and clean up resources."""
        if self.km is None:
            return

        try:
            logger.debug("Terminating kernel...")

            # Close client channels first
            if self.kc is not None:
                try:
                    self.kc.stop_channels()
                except Exception as e:
                    logger.warning(f"Error stopping channels: {str(e)}")
                self.kc = None

            # Shutdown the kernel
            shutdown_result = self.km.shutdown_kernel(now=True)
            await self._await_shutdown(shutdown_result)
            self.km = None

            logger.debug("Kernel terminated")
        except Exception as e:
            logger.warning(f"Error during kernel termination: {str(e)}")
            self.kc = None
            self.km = None

    async def reset(self) -> None:
        """Reset the kernel completely by terminating and creating a new one."""
        if self.workspace is None:
            return

        logger.info("Resetting kernel...")
        await self.terminate()
        await asyncio.sleep(1.5)
        await self.init(self.workspace)
        logger.info("Kernel reset complete")

    async def _await_shutdown(self, shutdown_result: Any) -> None:
        """Await shutdown result if it's awaitable."""
        try:
            if inspect.isawaitable(shutdown_result):
                await shutdown_result
            elif shutdown_result is not None and hasattr(shutdown_result, "result"):
                await shutdown_result.result()
        except Exception as e:
            logger.warning(f"Error during async shutdown: {str(e)}")

    def get_client(self) -> Optional[KernelClient]:
        """Get the kernel client."""
        return self.kc

    def is_ready(self) -> bool:
        """Check if kernel is ready."""
        return self.km is not None and self.kc is not None

    def interrupt(self) -> None:
        """Interrupt the running kernel execution."""
        if self.km is None:
            return
        try:
            self.km.interrupt_kernel()
            logger.debug("Kernel execution interrupted")
        except Exception as e:
            logger.warning(f"Error interrupting kernel: {str(e)}")

"""Jupyter Notebook integration module for AutoDS.

This module provides functionality for programmatically interacting with Jupyter notebooks,
including executing code, displaying rich outputs, and managing notebook cells and kernels.
It enables the execution of Python code and rendering of markdown content within notebooks,
handling various types of outputs including text, images, and error messages.

The main class, JupyterExecutor, provides a comprehensive interface for notebook operations,
while utility functions handle specific tasks like output formatting and display.
"""

import asyncio
import atexit
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

import nbformat
from nbclient.client import KernelClient
from nbformat import NotebookNode
from nbformat.v4 import (
    new_code_cell,
    new_markdown_cell,
    new_notebook,
    new_output,
    output_from_msg,
)

from autods.tools.base import Observation

from .display_utils import display_code
from .kernel_management import KernelManagement
from .output_handling import OutputParser, OutputTruncator
from .utility_functions import (
    EXECUTION_TIMEOUT_SECONDS,
    detect_ipython,
    shutdown_all_kernels,
)
from .utility_functions import display_image as display_image_util

logger = logging.getLogger(__name__)

INSTALL_KEEPLEN = 500

# Keep track of active executor instances for cleanup on exit
active_executors: list["JupyterExecutor"] = []


class JupyterExecutor:
    """
    A class for executing code in Jupyter notebooks programmatically.

    This executor can handle both Python code and markdown cells, managing the kernel
    lifecycle and providing rich output display capabilities. It saves executed notebooks
    to the specified workspace directory.

    Attributes:
        nb (NotebookNode): The notebook object containing cells and metadata.
        workspace (Path): Directory path where notebooks and related files are stored.
        km (Optional[KernelManager]): The kernel manager for this notebook.
        kc (Optional[KernelClient]): The kernel client for this notebook.
        console (Console): Rich console for displaying outputs.
        interaction (Literal["ipython", None]): Indicates if running in IPython environment.
    """

    def __init__(
        self,
        workspace: Path,
        nb: Optional[NotebookNode] = None,
        env_vars: dict[str, str] | None = None,
    ):
        """
        Initialize a new JupyterExecutor instance.

        Args:
            workspace (Path): Directory path where notebooks and related files are stored.
            nb (NotebookNode, optional): Existing notebook to use. Defaults to a new notebook.
        """
        self.workspace = workspace
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.nb_path = self.workspace / "code.ipynb"

        self.nb = self._load_or_create_notebook(nb)
        self._notebook_replayed = not self._has_code_cells_to_replay()

        self.kernel_manager = KernelManagement(env_vars)
        from rich.console import Console

        self.console = Console()
        self.interaction: Literal["ipython", None] = (
            "ipython" if detect_ipython() else None
        )
        self.env_vars = env_vars

        active_executors.append(self)

    def _ensure_ipykernel_installed(self) -> None:
        """Ensure the target interpreter can launch an ipykernel."""
        if not self.env_vars or "VIRTUAL_ENV" not in self.env_vars:
            return

        venv_dir = Path(self.env_vars["VIRTUAL_ENV"])
        python = venv_dir / ("Scripts" if os.name == "nt" else "bin") / (
            "python.exe" if os.name == "nt" else "python"
        )
        python_executable = str(python if python.exists() else Path(sys.executable))
        env = dict(self.env_vars)

        install_result = subprocess.run(
            [python_executable, "-m", "pip", "install", "ipykernel"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        if install_result.returncode == 0:
            return

        output = (install_result.stderr or install_result.stdout or "").strip()
        if len(output) > INSTALL_KEEPLEN * 2:
            output = output[:INSTALL_KEEPLEN] + "..." + output[-INSTALL_KEEPLEN:]
        raise RuntimeError(f"Failed to install ipykernel: {output}")

    def _load_or_create_notebook(self, nb: Optional[NotebookNode]) -> NotebookNode:
        """Load existing notebook or create a new one."""
        if nb is not None:
            return nb

        if self.nb_path.exists():
            try:
                loaded_nb = nbformat.read(self.nb_path, as_version=4)
                logger.debug("Loaded existing notebook from %s", self.nb_path)
                return loaded_nb
            except Exception as exc:
                logger.warning(
                    "Failed to load existing notebook at %s: %s", self.nb_path, exc
                )

        return new_notebook()

    def _has_code_cells_to_replay(self) -> bool:
        """Check if notebook has code cells and exists on disk."""
        has_code_cells = any(
            getattr(cell, "cell_type", None) == "code" for cell in self.nb.cells
        )
        return has_code_cells and self.nb_path.exists()

    async def _ensure_notebook_replayed(self) -> None:
        """Replay existing notebook cells if not already done."""
        if self._notebook_replayed:
            return

        logger.info("Replaying existing notebook cells from %s", self.nb_path)
        failures: List[Tuple[int, str]] = []

        for idx, cell in enumerate(self.nb.cells):
            if getattr(cell, "cell_type", None) != "code":
                continue

            try:
                success, output, _ = await self.run_cell(cell, idx)
                if not success:
                    logger.warning(
                        "Skipping notebook cell %s during replay due to failure: %s",
                        idx,
                        output,
                    )
                    failures.append((idx, output))
            except Exception as exc:
                logger.warning("Error while replaying notebook cell %s: %s", idx, exc)
                failures.append((idx, str(exc)))

        self._notebook_replayed = True

        if failures:
            logger.warning(
                "Notebook replay completed with %s failed cell(s): %s",
                len(failures),
                ", ".join(str(idx) for idx, _ in failures),
            )
        else:
            logger.info("Notebook replay complete")

    async def init_kernel(self) -> None:
        """Initialize the kernel if needed."""
        self._ensure_ipykernel_installed()
        await self.kernel_manager.init(self.workspace)

    async def terminate(self) -> None:
        """Terminate the running kernel and clean up resources."""
        await self.kernel_manager.terminate()

    async def reset(self) -> None:
        """Reset the kernel completely."""
        await self.kernel_manager.reset()

        self._notebook_replayed = not any(
            getattr(cell, "cell_type", None) == "code" for cell in self.nb.cells
        )

    def add_code_cell(self, code: str) -> None:
        """Add a new code cell to the notebook."""
        self.nb.cells.append(new_code_cell(source=code))

    def add_markdown_cell(self, markdown: str) -> None:
        """Add a new markdown cell to the notebook."""
        self.nb.cells.append(new_markdown_cell(source=markdown))

    def display_image(
        self, image_base64: str, interaction_type: Literal["ipython", None]
    ) -> None:
        """Display a figure from base64-encoded image data."""
        display_image_util(image_base64, interaction_type)

    def parse_outputs(
        self,
        outputs: List[Dict[str, Any]],
        keep_len: int = 5000,
        save_path: Optional[Path] = None,
    ) -> Tuple[bool, str, List[str]]:
        """Parse the outputs from a cell execution.

        Args:
            outputs: List of output dictionaries from cell execution.
            keep_len: Maximum length to keep for truncated output.
            save_path: Optional path to save full output when truncated.

        Returns:
            Tuple of (is_success, combined_output, images).
        """
        return OutputParser.parse(outputs, self, keep_len, save_path)

    async def run_cell(
        self,
        cell: NotebookNode,
        cell_id: int,
        timeout: float | None = None,
        save_path: Optional[Path] = None,
    ) -> Tuple[bool, str, List[str]]:
        """Execute a single notebook cell using our persistent kernel.

        Args:
            cell: The notebook cell to execute.
            cell_id: The index of the cell in the notebook.
            timeout: Optional timeout in seconds for cell execution.
            save_path: Optional path to save full output when truncated.

        Returns:
            Tuple of (is_success, output, images).
        """
        await self.init_kernel()

        kernel_client = self.kernel_manager.get_client()
        if kernel_client is None:
            error_msg = "Kernel client not initialized"
            logger.error(error_msg)
            return False, error_msg, []

        try:
            msg_id = kernel_client.execute(cell.source)
            outputs = await self._collect_cell_outputs(kernel_client, msg_id, timeout)
            cell["outputs"] = outputs
            return self.parse_outputs(outputs, save_path=save_path)
        except Exception as e:
            error_msg = str(e) or f"Unknown error ({type(e).__name__})"
            logger.error(f"Error executing cell: {error_msg}")
            error_output = new_output(
                output_type="error",
                ename=type(e).__name__,
                evalue=error_msg,
                traceback=[error_msg],
            )
            cell["outputs"] = [error_output]
            return False, error_msg, []

    async def _collect_outputs_loop(
        self, kernel_client: KernelClient, msg_id: str, timeout: float
    ) -> List[Dict[str, Any]]:
        """Inner loop that collects outputs from kernel messages with deadline enforcement."""
        deadline = time.monotonic() + timeout
        outputs: List[Dict[str, Any]] = []

        while True:
            # Check deadline BEFORE calling ZMQ
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                logger.warning("Cell execution timed out after %s seconds", timeout)
                self.kernel_manager.interrupt()
                raise TimeoutError(
                    f"Cell execution timed out after {timeout} seconds. Consider: "
                    "1) Increasing CPU and GPU utilization (cpu_limit=os.cpu_count()),"
                    "2) Breaking the task into smaller subtasks."
                    "NEVER simplify approach. Goal is to be more efficient NOT simpler.\n"
                    "Be more aggressive in CPU/GPU utilization, and effective in memory management (pd.read_csv(..., chunksize=100_000))."
                )
            try:
                # Poll with 10s interval to check deadline regularly
                msg = await kernel_client._async_get_iopub_msg(
                    timeout=min(remaining, 10.0)
                )

                if msg["parent_header"].get("msg_id") != msg_id:
                    continue

                msg_type = msg["header"]["msg_type"]
                content = msg["content"]

                if msg_type == "status" and content["execution_state"] == "idle":
                    break

                if msg_type in ("execute_result", "display_data", "stream", "error"):
                    outputs.append(output_from_msg(msg))

            except asyncio.TimeoutError:
                # Polling interval elapsed, loop will check deadline on next iteration
                continue
            except Exception as e:
                error_msg = str(e) or type(e).__name__
                error_msg_lower = error_msg.lower()

                # Treat "Empty" messages as normal timeouts (kernel is busy, no message yet)
                if "empty" in error_msg_lower:
                    logger.debug(
                        "No kernel message available yet (Empty), kernel may be busy with computation"
                    )
                    continue

                # For other exceptions, treat as actual communication failure
                raise RuntimeError(
                    f"Kernel communication failed: {error_msg}. "
                    "The kernel may have crashed due to memory issues or an internal error."
                ) from e

        return outputs

    async def _collect_cell_outputs(
        self, kernel_client: KernelClient, msg_id: str, timeout: float | None = None
    ) -> List[Dict[str, Any]]:
        """Collect outputs from kernel messages with total execution timeout."""
        timeout_seconds = timeout if timeout is not None else EXECUTION_TIMEOUT_SECONDS
        return await self._collect_outputs_loop(kernel_client, msg_id, timeout_seconds)

    async def run(
        self,
        code: str,
        language: Literal["python", "markdown"] = "python",
        timeout: float | None = None,
    ) -> Observation:
        """Run code in the notebook.

        Args:
            code: The code to execute.
            language: The language of the code ("python" or "markdown").
            timeout: Optional timeout in seconds for cell execution.
                     If None, uses the default EXECUTION_TIMEOUT_SECONDS.
        """
        try:
            await self._ensure_notebook_replayed()
        except Exception as replay_error:
            message = (
                f"Failed to replay existing notebook before execution: {replay_error}"
            )
            return Observation(is_success=False, message=message, base64_images=[])

        display_code(code, self.console, language)

        try:
            if language == "python":
                return await self._run_python(code, timeout)
            elif language == "markdown":
                return self._run_markdown(code)
            else:
                raise ValueError(
                    f"Only support for language: python, markdown, but got {language}"
                )
        except KeyboardInterrupt:
            logger.warning("Operation interrupted by user")
            return Observation(
                is_success=False,
                message="Operation interrupted by user",
                base64_images=[],
            )
        except TimeoutError as e:
            logger.warning("Notebook execution timed out: %s", e)
            return Observation(
                is_success=False,
                message=str(e),
                base64_images=[],
            )
        except Exception as e:
            logger.error(f"Error executing code: {str(e)}")
            return Observation(
                is_success=False,
                message=f"Error: {str(e)}",
                base64_images=[],
            )
        finally:
            self._save_notebook()

    async def _run_python(self, code: str, timeout: float | None = None) -> Observation:
        """Execute Python code."""
        self.add_code_cell(code=code)
        cell_index = len(self.nb.cells) - 1

        # Generate output file path for this cell (for saving full output when truncated)
        output_dir = self.workspace / ".outputs"
        output_path = output_dir / f"cell_{cell_index}_{int(time.time())}.txt"

        success, output, images = await self.run_cell(
            self.nb.cells[-1], cell_index, timeout, save_path=output_path
        )

        if "!pip" in code:
            output = output[-INSTALL_KEEPLEN:]
        elif "git clone" in code:
            output = OutputTruncator.truncate_installer(output)

        return Observation(
            is_success=success,
            message=output,
            base64_images=[f"data:image/png;base64,{image}" for image in images],
        )

    def _run_markdown(self, code: str) -> Observation:
        """Add markdown content to notebook."""
        self.add_markdown_cell(code)
        return Observation(is_success=True, message=code, base64_images=[])

    def _save_notebook(self) -> None:
        """Save the notebook to disk."""
        try:
            file_path = self.workspace / "code.ipynb"
            nbformat.write(self.nb, file_path)
        except Exception as e:
            logger.error(f"Error saving notebook: {str(e)}")

    async def __aenter__(self):
        """Async context manager entry point."""
        await self.init_kernel()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit point that ensures proper cleanup."""
        await self.terminate()
        return False


# Register the cleanup function to run at exit
atexit.register(shutdown_all_kernels, active_executors)

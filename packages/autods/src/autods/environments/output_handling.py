"""Output handling module for Jupyter executor.

This module contains classes and functions for handling output truncation,
parsing, and display in Jupyter notebook execution.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_KEEP_LEN = 5000
INSTALL_KEEPLEN = 500


class OutputTruncator:
    """Handles output truncation logic for different types of content."""

    @classmethod
    def truncate(cls, text: str, keep_len: int, save_path: Optional[Path] = None) -> str:
        """Return head+tail of text if it exceeds keep_len characters.

        Args:
            text: The text to truncate.
            keep_len: Maximum length to keep (head + tail).
            save_path: Optional path to save full output when truncated.

        Returns:
            Truncated text with ellipsis marker showing omitted chars count
            and file path reference if save_path was provided.
        """
        if not text or len(text) <= keep_len:
            return text

        # Save full output to file if path provided
        file_ref = ""
        if save_path:
            try:
                save_path.parent.mkdir(parents=True, exist_ok=True)
                save_path.write_text(text)
                file_ref = f" Full output: {save_path}"
            except Exception as e:
                logger.warning(f"Failed to save full output to {save_path}: {e}")

        half = max(1, keep_len // 2)
        omitted = len(text) - (2 * half)
        ellipsis = f"\n... [{omitted} chars truncated.{file_ref}] ...\n"
        return text[:half] + ellipsis + text[-half:]

    @classmethod
    def truncate_installer(cls, output: str) -> str:
        """Truncate output from package installers."""
        return output[:INSTALL_KEEPLEN] + "..." + output[-INSTALL_KEEPLEN:]


class OutputParser:
    """Handles parsing and processing of notebook cell outputs."""

    @staticmethod
    def parse(
        outputs: List[Dict[str, Any]],
        executor,
        keep_len: int = DEFAULT_OUTPUT_KEEP_LEN,
        save_path: Optional[Path] = None,
    ) -> Tuple[bool, str, List[str]]:
        """Parse outputs from a cell execution.

        Args:
            outputs: List of output dictionaries from cell execution.
            executor: JupyterExecutor instance for image display.
            keep_len: Maximum length to keep for truncated output.
            save_path: Optional path to save full output when truncated.

        Returns:
            Tuple of (is_success, combined_output, images).
        """
        assert isinstance(outputs, list)
        parsed_output, is_success = [], True
        images: List[str] = []

        for output in outputs:
            output_type = output["output_type"]
            output_text = OutputParser._parse_single_output(output, images, executor)

            if output_type == "error":
                is_success = False
            elif output_text.strip().startswith("<coroutine object"):
                output_text = "Executed code failed, you need use key word 'await' to run a async code."
                is_success = False

            output_text = OutputParser._strip_ansi_codes(output_text)
            if is_success:
                output_text = OutputParser._filter_log_lines(output_text)

            parsed_output.append(output_text)

        combined = "\n".join([p for p in parsed_output if p])

        # Truncate the COMBINED output to keep_len, saving full output to file if path provided
        if keep_len > 0:
            combined = OutputTruncator.truncate(combined, keep_len, save_path)

        return is_success, combined, images

    @staticmethod
    def _parse_single_output(output: Dict[str, Any], images: List[str], executor) -> str:
        """Parse a single output based on its type."""
        output_type = output["output_type"]

        if output_type == "display_data":
            return OutputParser._handle_display_data(output, images, executor)
        elif output_type == "execute_result":
            return output["data"]["text/plain"]
        elif output_type == "stream":
            return output.get("text", "")
        elif output_type == "error":
            return "\n".join(output["traceback"])

        return ""

    @staticmethod
    def _handle_display_data(output: Dict[str, Any], images: List[str], executor) -> str:
        """Handle display_data output type."""
        if "image/png" in output["data"]:
            executor.display_image(output["data"]["image/png"], executor.interaction)
            images.append(output["data"]["image/png"])
            return ""
        else:
            logger.info("display_data output doesn't have image/png, skipping...")
            return ""

    @staticmethod
    def _strip_ansi_codes(input_str: str) -> str:
        """Remove ANSI escape sequences and color codes from text output."""
        pattern = re.compile(r"\x1b\[[0-9;]*[mK]")
        result = pattern.sub("", input_str)
        return result

    @staticmethod
    def _filter_log_lines(input_str: str) -> str:
        """Remove log and warning lines from the output string."""
        delete_lines = ["[warning]", "warning:", "[cv]", "[info]"]
        result = "\n".join(
            [line for line in input_str.split("\n") if not any(dl in line.lower() for dl in delete_lines)]
        ).strip()
        return result

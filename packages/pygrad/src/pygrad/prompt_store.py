"""Prompt loading utilities."""

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=32)
def _read_file(abs_path: str) -> str:
    """Read and cache file contents."""
    return Path(abs_path).read_text()


class PromptStore:
    """Store for loading prompt templates."""

    def __init__(self, base_path: Path | None = None):
        if base_path is None:
            self.base_path = Path(__file__).parent / "prompts"
        else:
            self.base_path = Path(base_path)

    def load(self, relative_path: str | Path) -> str:
        """Load a prompt file by relative path.

        Args:
            relative_path: Path relative to the prompts directory

        Returns:
            Contents of the prompt file

        Raises:
            ValueError: If path escapes the base directory
            FileNotFoundError: If prompt file doesn't exist
        """
        relative_path = Path(relative_path)
        base = self.base_path.resolve()
        abs_file_path = (base / relative_path).resolve()

        if not abs_file_path.is_relative_to(base):
            raise ValueError(f"Path {relative_path} is outside base path {self.base_path}")
        if not abs_file_path.exists():
            raise FileNotFoundError(f"Prompt file {abs_file_path} does not exist")

        return _read_file(str(abs_file_path))


prompt_store = PromptStore()

from functools import lru_cache
from pathlib import Path
from typing import Optional


@lru_cache(maxsize=None)
def _read_file(abs_path: str) -> str:
    return Path(abs_path).read_text()


class PromptStore:
    def __init__(self, base_path: Optional[str | Path] = None):
        if base_path is None:
            self.base_path = Path(__file__).parent / "prompts"
        else:
            self.base_path = Path(base_path)

    def load(self, relative_path: str | Path) -> str:
        relative_path = Path(relative_path)
        base = self.base_path.resolve()
        abs_file_path = (base / relative_path).resolve()

        if not abs_file_path.is_relative_to(base):
            raise ValueError(
                f"Path {relative_path} is outside of base path {self.base_path}."
            )
        if not abs_file_path.exists():
            raise FileNotFoundError(f"File {abs_file_path} does not exist.")

        return _read_file(str(abs_file_path))


prompt_store = PromptStore()

"""Pygrad configuration and constants."""

from pathlib import Path

# Default storage paths
PYGRAD_HOME = Path.home() / ".pygrad"
REPO_STORAGE = PYGRAD_HOME / "repos"


def ensure_storage_exists() -> Path:
    """Ensure the repository storage directory exists."""
    REPO_STORAGE.mkdir(parents=True, exist_ok=True)
    return REPO_STORAGE

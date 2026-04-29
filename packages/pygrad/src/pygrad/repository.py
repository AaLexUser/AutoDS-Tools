"""Repository cloning and identification utilities."""

import subprocess
from pathlib import Path
from urllib.parse import urlparse


def get_repository_id(url: str) -> str:
    """Extract a unique repository ID from a GitHub URL.

    Args:
        url: GitHub repository URL (e.g., https://github.com/owner/repo)

    Returns:
        Repository ID in format "owner-repo" (lowercase)

    Raises:
        RuntimeError: If the URL is not a valid GitHub URL
    """
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.strip("/").split("/")
    if len(path_parts) < 2:
        raise RuntimeError(f"Invalid GitHub URL format. Expected: https://github.com/owner/repo. Got: {url}")
    owner, repo_name = path_parts[-2:]
    return f"{owner.lower()}-{repo_name.lower()}"


def clone_repository(url: str, path: str | Path) -> None:
    """Clone a Git repository to the specified path.

    Args:
        url: Git repository URL
        path: Local path to clone to

    Raises:
        RuntimeError: If cloning fails
    """
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", url, str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Failed to clone repository from {url}: {e.stderr}. "
            f"Please provide a valid git URL or ensure the repository exists."
        ) from e

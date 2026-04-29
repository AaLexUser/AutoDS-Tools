"""Tests for repository utilities."""

import pytest

from pygrad.repository import clone_repository, get_repository_id


class TestGetRepositoryId:
    """Tests for get_repository_id function."""

    def test_standard_github_url(self):
        """Test parsing a standard GitHub URL."""
        url = "https://github.com/owner/repo"
        assert get_repository_id(url) == "owner-repo"

    def test_github_url_with_trailing_slash(self):
        """Test parsing URL with trailing slash."""
        url = "https://github.com/owner/repo/"
        assert get_repository_id(url) == "owner-repo"

    def test_github_url_with_git_extension(self):
        """Test parsing URL with .git extension."""
        url = "https://github.com/owner/repo.git"
        # The .git is part of the repo name
        assert get_repository_id(url) == "owner-repo.git"

    def test_github_url_uppercase_normalized(self):
        """Test that URLs are normalized to lowercase."""
        url = "https://github.com/OWNER/REPO"
        assert get_repository_id(url) == "owner-repo"

    def test_invalid_url_too_short(self):
        """Test that invalid URLs raise RuntimeError."""
        url = "https://github.com/owner"
        with pytest.raises(RuntimeError, match="Invalid GitHub URL format"):
            get_repository_id(url)

    def test_empty_path(self):
        """Test URL with empty path."""
        url = "https://github.com/"
        with pytest.raises(RuntimeError, match="Invalid GitHub URL format"):
            get_repository_id(url)


class TestCloneRepository:
    """Tests for clone_repository function."""

    def test_clone_invalid_url_raises_error(self, temp_dir):
        """Test that cloning from invalid URL raises RuntimeError."""
        url = "https://github.com/definitely-not-a-real-owner/definitely-not-a-real-repo"
        with pytest.raises(RuntimeError, match="Failed to clone repository"):
            clone_repository(url, temp_dir / "cloned_repo")

    def test_clone_empty_url_raises_error(self, temp_dir):
        """Test that empty URL raises RuntimeError."""
        with pytest.raises(RuntimeError, match="Failed to clone repository"):
            clone_repository("", temp_dir / "cloned_repo")

    # Note: We don't test actual successful cloning as it would require network access
    # and would slow down tests. Integration tests should cover that separately.

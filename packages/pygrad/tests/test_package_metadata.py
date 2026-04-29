"""Tests for packaging metadata contracts."""

import tomllib
from pathlib import Path


def test_default_runtime_dependencies_include_python_dotenv() -> None:
    """Default install should support importing pygrad without extra packages."""
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]
    dependencies = project["dependencies"]

    assert "python-dotenv>=1.0.0" in dependencies

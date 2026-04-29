"""Tests for notebook example extractor."""

import json

import pytest

from pygrad.processor.notebook_extractor import (
    NotebookCell,
    NotebookExample,
    NotebookExampleExtractor,
    VariableTrack,
    extract_notebook_examples_from_repository,
)


@pytest.fixture
def sample_notebook(temp_dir):
    """Create a sample Jupyter notebook for testing."""
    notebook_content = {
        "cells": [
            {
                "cell_type": "markdown",
                "source": [
                    "# Example Notebook\n",
                    "\n",
                    "This notebook demonstrates usage.",
                ],
            },
            {
                "cell_type": "code",
                "source": ["from mypackage import Calculator"],
                "outputs": [],
                "execution_count": 1,
            },
            {
                "cell_type": "code",
                "source": ["calc = Calculator(initial_value=10)"],
                "outputs": [],
                "execution_count": 2,
            },
            {
                "cell_type": "code",
                "source": ["result = calc.add(5)\n", "print(result)"],
                "outputs": [{"output_type": "stream", "text": ["15"]}],
                "execution_count": 3,
            },
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }

    notebook_path = temp_dir / "example.ipynb"
    with open(notebook_path, "w") as f:
        json.dump(notebook_content, f)

    return notebook_path


@pytest.fixture
def api_elements():
    """Sample API elements for testing."""
    return {
        "mypackage.Calculator",
        "mypackage.Calculator.add",
        "mypackage.Calculator.__init__",
        "mypackage.helper_function",
    }


class TestNotebookExampleExtractor:
    """Tests for NotebookExampleExtractor class."""

    def test_build_simplified_mapping(self, api_elements, temp_dir):
        """Test that simplified mapping is built correctly."""
        extractor = NotebookExampleExtractor(str(temp_dir), api_elements)

        # "Calculator" should map to "mypackage.Calculator"
        assert "Calculator" in extractor.simplified_to_qualified
        assert "mypackage.Calculator" in extractor.simplified_to_qualified["Calculator"]

    def test_resolve_api_path_exact(self, api_elements, temp_dir):
        """Test resolving exact API path."""
        extractor = NotebookExampleExtractor(str(temp_dir), api_elements)

        result = extractor._resolve_api_path("mypackage.Calculator")
        assert result == "mypackage.Calculator"

    def test_resolve_api_path_simplified(self, api_elements, temp_dir):
        """Test resolving simplified API path."""
        extractor = NotebookExampleExtractor(str(temp_dir), api_elements)

        result = extractor._resolve_api_path("Calculator")
        assert result == "mypackage.Calculator"

    def test_resolve_api_path_unknown(self, api_elements, temp_dir):
        """Test resolving unknown API path."""
        extractor = NotebookExampleExtractor(str(temp_dir), api_elements)

        result = extractor._resolve_api_path("UnknownClass")
        assert result is None

    def test_extract_from_notebook(self, sample_notebook, api_elements):
        """Test extracting examples from a notebook."""
        extractor = NotebookExampleExtractor(str(sample_notebook.parent), api_elements)

        examples = extractor.extract_from_notebook(str(sample_notebook))

        # Should find the Calculator usage
        assert len(examples) >= 1

        # Check that the example has the correct API path
        api_paths = {ex.api_path for ex in examples}
        assert "mypackage.Calculator" in api_paths

    def test_format_example(self, sample_notebook, api_elements):
        """Test formatting an example."""
        extractor = NotebookExampleExtractor(str(sample_notebook.parent), api_elements)

        examples = extractor.extract_from_notebook(str(sample_notebook))

        if examples:
            formatted = extractor.format_example(examples[0])
            assert isinstance(formatted, str)
            assert len(formatted) > 0


class TestNotebookDataClasses:
    """Tests for notebook data classes."""

    def test_notebook_cell_creation(self):
        """Test NotebookCell dataclass."""
        cell = NotebookCell(
            cell_type="code",
            index=0,
            source="x = 1",
            outputs=["1"],
            execution_count=1,
        )

        assert cell.cell_type == "code"
        assert cell.index == 0
        assert cell.source == "x = 1"

    def test_variable_track_creation(self):
        """Test VariableTrack dataclass."""
        track = VariableTrack(
            api_path="pkg.Class",
            variable_name="obj",
            import_cell_idx=0,
            init_cell_idx=1,
        )

        assert track.api_path == "pkg.Class"
        assert track.variable_name == "obj"
        assert not track.is_direct_usage

    def test_notebook_example_creation(self):
        """Test NotebookExample dataclass."""
        example = NotebookExample(
            source_file="test.ipynb",
            api_path="pkg.Class",
        )

        assert example.source_file == "test.ipynb"
        assert example.example_type == "notebook"


class TestExtractNotebookExamplesFromRepository:
    """Tests for the convenience function."""

    def test_extract_with_no_notebooks(self, temp_dir):
        """Test extraction when no notebooks exist."""
        api_elements = {"pkg.Class"}

        examples = extract_notebook_examples_from_repository(str(temp_dir), api_elements)

        assert examples == []

    def test_extract_with_empty_api_elements(self, sample_notebook):
        """Test extraction with empty API elements."""
        examples = extract_notebook_examples_from_repository(str(sample_notebook.parent), set())

        assert examples == []

    def test_extract_with_specific_paths(self, sample_notebook, api_elements):
        """Test extraction with specific notebook paths."""
        examples = extract_notebook_examples_from_repository(
            str(sample_notebook.parent),
            api_elements,
            notebook_paths=[str(sample_notebook)],
        )

        # Should find examples from the specified notebook
        assert isinstance(examples, list)

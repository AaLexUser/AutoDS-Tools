"""Tests for markdown example extractor."""

import pytest

from pygrad.processor.markdown_extractor import (
    MarkdownCodeBlock,
    MarkdownExample,
    MarkdownExampleExtractor,
    extract_markdown_examples_from_repository,
)


@pytest.fixture
def sample_markdown(temp_dir):
    """Create a sample Markdown file for testing."""
    content = """# Getting Started

This is an example of how to use the Calculator class.

## Basic Usage

Here's how to create a calculator:

```python
from mypackage import Calculator

calc = Calculator(initial_value=0)
result = calc.add(5)
print(result)
```

## Advanced Usage

You can chain operations:

```python
calc = Calculator()
calc.add(10)
calc.add(20)
```

## Not Python

This block should be ignored:

```bash
pip install mypackage
```
"""
    file_path = temp_dir / "README.md"
    file_path.write_text(content)
    return file_path


@pytest.fixture
def api_elements():
    """Sample API elements for testing."""
    return {
        "mypackage.Calculator",
        "mypackage.Calculator.add",
        "mypackage.Calculator.__init__",
    }


class TestMarkdownExampleExtractor:
    """Tests for MarkdownExampleExtractor class."""

    def test_build_simplified_mapping(self, api_elements, temp_dir):
        """Test that simplified mapping is built correctly."""
        extractor = MarkdownExampleExtractor(str(temp_dir), api_elements)

        assert "Calculator" in extractor.simplified_to_qualified
        assert "mypackage.Calculator" in extractor.simplified_to_qualified["Calculator"]

    def test_resolve_api_path_exact(self, api_elements, temp_dir):
        """Test resolving exact API path."""
        extractor = MarkdownExampleExtractor(str(temp_dir), api_elements)

        result = extractor._resolve_api_path("mypackage.Calculator")
        assert result == "mypackage.Calculator"

    def test_resolve_api_path_simplified(self, api_elements, temp_dir):
        """Test resolving simplified API path."""
        extractor = MarkdownExampleExtractor(str(temp_dir), api_elements)

        result = extractor._resolve_api_path("Calculator")
        assert result == "mypackage.Calculator"

    def test_resolve_api_path_unknown(self, api_elements, temp_dir):
        """Test resolving unknown API path."""
        extractor = MarkdownExampleExtractor(str(temp_dir), api_elements)

        result = extractor._resolve_api_path("UnknownClass")
        assert result is None

    def test_extract_from_markdown(self, sample_markdown, api_elements):
        """Test extracting examples from a markdown file."""
        extractor = MarkdownExampleExtractor(str(sample_markdown.parent), api_elements)

        examples = extractor.extract_from_markdown(str(sample_markdown))

        # Should find Python code blocks with Calculator usage
        assert len(examples) >= 1

        # Check that examples contain the expected API paths
        all_api_paths = set()
        for ex in examples:
            all_api_paths.update(ex.api_paths)

        assert "mypackage.Calculator" in all_api_paths

    def test_extract_code_blocks(self, sample_markdown, api_elements):
        """Test extracting code blocks from markdown."""
        extractor = MarkdownExampleExtractor(str(sample_markdown.parent), api_elements)

        with open(sample_markdown) as f:
            content = f.read()

        blocks = extractor._extract_code_blocks(content, str(sample_markdown))

        # Should find 3 code blocks (2 python, 1 bash)
        assert len(blocks) == 3

        # Check that headers are extracted
        python_blocks = [b for b in blocks if b.language.lower() in ["python", "py"]]
        assert len(python_blocks) == 2

        # First python block should have a header (either Basic Usage or the parent header)
        assert python_blocks[0].preceding_header is not None

    def test_find_preceding_context(self, sample_markdown, api_elements):
        """Test finding preceding context for code blocks."""
        extractor = MarkdownExampleExtractor(str(sample_markdown.parent), api_elements)

        # Test with header directly before code block
        lines = [
            "# Header",
            "",
            "```python",
            "code here",
            "```",
        ]

        header, _text = extractor._find_preceding_context(lines, 2)

        assert header == "Header"

        # Test with text between header and code
        lines2 = [
            "# Header",
            "Some text description.",
            "```python",
            "code here",
            "```",
        ]

        _header2, text2 = extractor._find_preceding_context(lines2, 2)

        assert text2 == "Some text description."


class TestMarkdownDataClasses:
    """Tests for markdown data classes."""

    def test_markdown_code_block_creation(self):
        """Test MarkdownCodeBlock dataclass."""
        block = MarkdownCodeBlock(
            source_file="README.md",
            code="x = 1",
            language="python",
            start_line=10,
            end_line=12,
            preceding_header="Example",
            preceding_text="Description",
        )

        assert block.source_file == "README.md"
        assert block.language == "python"
        assert block.preceding_header == "Example"

    def test_markdown_example_creation(self):
        """Test MarkdownExample dataclass."""
        example = MarkdownExample(
            source_file="README.md",
            api_paths={"pkg.Class"},
            code="x = Class()",
            header="Usage",
            description="How to use",
        )

        assert example.source_file == "README.md"
        assert example.example_type == "readme"
        assert "pkg.Class" in example.api_paths


class TestExtractMarkdownExamplesFromRepository:
    """Tests for the convenience function."""

    def test_extract_with_no_markdown(self, temp_dir):
        """Test extraction when no markdown files exist."""
        # Create an empty subdirectory
        subdir = temp_dir / "empty"
        subdir.mkdir()

        api_elements = {"pkg.Class"}

        examples = extract_markdown_examples_from_repository(str(subdir), api_elements)

        assert examples == []

    def test_extract_with_empty_api_elements(self, sample_markdown):
        """Test extraction with empty API elements."""
        examples = extract_markdown_examples_from_repository(str(sample_markdown.parent), set())

        assert examples == []

    def test_extract_with_specific_paths(self, sample_markdown, api_elements):
        """Test extraction with specific markdown paths."""
        examples = extract_markdown_examples_from_repository(
            str(sample_markdown.parent),
            api_elements,
            markdown_paths=[str(sample_markdown)],
        )

        assert len(examples) >= 1

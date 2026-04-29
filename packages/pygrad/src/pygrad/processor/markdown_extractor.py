"""Extract usage examples from Markdown files.

This module provides functionality to extract self-contained usage examples
from Markdown documentation files (like README.md), tracking code blocks
and their associated documentation context.
"""

import ast
import re
import warnings
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import cast


@dataclass
class MarkdownCodeBlock:
    """Represents a Python code block from a Markdown file."""

    source_file: str
    code: str
    language: str  # e.g., "python", "py"
    start_line: int
    end_line: int
    preceding_header: str | None = None
    preceding_text: str | None = None


@dataclass
class MarkdownExample:
    """Represents an extracted example from a Markdown file."""

    source_file: str
    api_paths: set[str]  # All API paths mentioned in the code block
    code: str
    header: str | None = None
    description: str | None = None
    example_type: str = "readme"


class MarkdownExampleExtractor:
    """Extracts usage examples from Markdown files."""

    def __init__(self, repo_path: str, api_elements: set[str]):
        """Initialize the markdown example extractor.

        Args:
            repo_path: Path to the repository root
            api_elements: Set of known API elements to track (fully qualified names)
        """
        self.repo_path = Path(repo_path)
        self.api_elements = api_elements
        self.simplified_to_qualified = self._build_simplified_mapping(api_elements)

    def _build_simplified_mapping(self, api_elements: set[str]) -> dict[str, set[str]]:
        """Build a mapping from simplified names to fully qualified API paths."""
        mapping: dict[str, set[str]] = defaultdict(set)

        for api_path in api_elements:
            parts = api_path.split(".")
            for i in range(len(parts)):
                suffix = ".".join(parts[i:])
                mapping[suffix].add(api_path)

        return dict(mapping)

    def _resolve_api_path(self, candidate_path: str) -> str | None:
        """Resolve a candidate API path to a fully qualified path if possible."""
        if candidate_path in self.api_elements:
            return candidate_path

        matches: set[str] | None = self.simplified_to_qualified.get(candidate_path)
        if matches is None:
            return None
        if len(matches) == 1:
            return next(iter(matches))
        return cast(str, min(matches, key=len))

    def extract_from_markdown(self, markdown_path: str) -> list[MarkdownExample]:
        """Extract examples from a single Markdown file."""
        with open(markdown_path, encoding="utf-8") as f:
            content = f.read()

        code_blocks = self._extract_code_blocks(content, markdown_path)

        examples: list[MarkdownExample] = []
        for block in code_blocks:
            if block.language.lower() in ("python", "py", "python3"):
                example = self._process_code_block(block)
                if example and example.api_paths:
                    examples.append(example)

        return examples

    def extract_from_markdowns(self, markdown_paths: list[str]) -> list[MarkdownExample]:
        """Extract examples from multiple Markdown files."""
        all_examples: list[MarkdownExample] = []

        for markdown_path in markdown_paths:
            try:
                all_examples.extend(self.extract_from_markdown(markdown_path))
            except Exception:
                continue

        return all_examples

    def _extract_code_blocks(self, content: str, source_file: str) -> list[MarkdownCodeBlock]:
        """Extract code blocks from Markdown content with their context."""
        blocks: list[MarkdownCodeBlock] = []
        lines = content.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i]

            fence_match = re.match(r"^```(\w+)?", line)
            if fence_match:
                language = fence_match.group(1) or "text"
                start_line = i + 1
                code_lines: list[str] = []

                header, text = self._find_preceding_context(lines, i)

                i += 1
                while i < len(lines):
                    if lines[i].strip().startswith("```"):
                        end_line = i - 1
                        code = "\n".join(code_lines)

                        block = MarkdownCodeBlock(
                            source_file=source_file,
                            code=code,
                            language=language,
                            start_line=start_line,
                            end_line=end_line,
                            preceding_header=header,
                            preceding_text=text,
                        )
                        blocks.append(block)
                        break

                    code_lines.append(lines[i])
                    i += 1

            i += 1

        return blocks

    def _find_preceding_context(self, lines: list[str], code_start_index: int) -> tuple[str | None, str | None]:
        """Find the preceding header and text paragraph before a code block."""
        header = None
        text_lines: list[str] = []

        i = code_start_index - 1

        while i >= 0:
            line = lines[i].strip()

            if not line:
                i -= 1
                if text_lines:
                    break
                continue

            header_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if header_match:
                header = header_match.group(2).strip()
                break

            text_lines.insert(0, line)
            i -= 1

        if header is None and i >= 0:
            i -= 1
            while i >= 0:
                line = lines[i].strip()

                if not line:
                    i -= 1
                    continue

                header_match = re.match(r"^(#{1,6})\s+(.+)$", line)
                if header_match:
                    header = header_match.group(2).strip()
                    break

                i -= 1

        text = " ".join(text_lines) if text_lines else None

        return header, text

    def _process_code_block(self, block: MarkdownCodeBlock) -> MarkdownExample | None:
        """Process a code block to extract API references."""
        try:
            imports = self._extract_imports_from_code(block.code)
            api_paths = self._find_api_references(block.code, imports)

            if not api_paths:
                return None

            formatted_code = self._format_example(block)

            return MarkdownExample(
                source_file=block.source_file,
                api_paths=api_paths,
                code=formatted_code,
                header=block.preceding_header,
                description=block.preceding_text,
                example_type="readme",
            )
        except Exception:
            return None

    def _extract_imports_from_code(self, code: str) -> dict[str, str]:
        """Extract import statements from code using AST."""
        imports: dict[str, str] = {}

        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=SyntaxWarning)
                tree = ast.parse(code)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        name = alias.asname if alias.asname else alias.name
                        imports[name] = alias.name

                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        name = alias.asname if alias.asname else alias.name
                        if module:
                            imports[name] = f"{module}.{alias.name}"
                        else:
                            imports[name] = alias.name

        except SyntaxError:
            pass

        return imports

    def _find_api_references(self, code: str, imports: dict[str, str]) -> set[str]:
        """Find all API element references in the code."""
        api_paths: set[str] = set()

        for imported_name, module_path in imports.items():
            resolved = self._resolve_api_path(module_path)
            if resolved:
                api_paths.add(resolved)

            resolved = self._resolve_api_path(imported_name)
            if resolved:
                api_paths.add(resolved)

        for api_element in self.api_elements:
            parts = api_element.split(".")
            last_part = parts[-1]

            pattern = r"\b" + re.escape(last_part) + r"\b"
            if re.search(pattern, code):
                usage_pattern = r"\b" + re.escape(last_part) + r"\s*\("
                if re.search(usage_pattern, code):
                    api_paths.add(api_element)

        return api_paths

    def _format_example(self, block: MarkdownCodeBlock) -> str:
        """Format a code block as an example with header/description as comments."""
        lines: list[str] = []

        if block.preceding_header:
            lines.append(f"# {block.preceding_header}")
            lines.append("")

        if block.preceding_text:
            text = block.preceding_text
            max_line_length = 80

            words = text.split()
            current_line = "#"

            for word in words:
                if len(current_line) + len(word) + 1 > max_line_length:
                    lines.append(current_line)
                    current_line = f"# {word}"
                else:
                    if current_line == "#":
                        current_line = f"# {word}"
                    else:
                        current_line += f" {word}"

            if current_line != "#":
                lines.append(current_line)

            lines.append("")

        lines.append(block.code)

        return "\n".join(lines)


def extract_markdown_examples_from_repository(
    repo_path: str, api_elements: set[str], markdown_paths: list[str] | None = None
) -> list[MarkdownExample]:
    """Extract examples from Markdown files in a repository.

    Args:
        repo_path: Path to the repository
        api_elements: Set of known API elements to track
        markdown_paths: Optional list of specific markdown file paths.
                       If None, will search for all .md files in repo.

    Returns:
        List of MarkdownExample objects
    """
    extractor = MarkdownExampleExtractor(repo_path, api_elements)

    if markdown_paths is None:
        repo_path_obj = Path(repo_path)
        markdown_paths = [str(p) for p in repo_path_obj.rglob("*.md")]

    return extractor.extract_from_markdowns(markdown_paths)

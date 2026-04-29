"""Extract usage examples from Jupyter notebooks.

This module provides functionality to extract self-contained usage examples
from Jupyter notebooks, tracking import-initialization-usage patterns for
library classes and functions.
"""

import ast
import json
import re
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast


@dataclass
class NotebookCell:
    """Represents a single cell in a Jupyter notebook."""

    cell_type: str  # "code", "markdown"
    index: int
    source: str
    outputs: list[str] = field(default_factory=list)
    execution_count: int | None = None


@dataclass
class VariableTrack:
    """Tracks the usage of a variable through notebook cells."""

    api_path: str  # Fully qualified API path (e.g., "module.Class")
    variable_name: str
    import_cell_idx: int
    init_cell_idx: int
    usage_cell_indices: set[int] = field(default_factory=set)
    is_direct_usage: bool = False  # True if initialization coincides with usage


@dataclass
class NotebookExample:
    """Represents an extracted example from a notebook."""

    source_file: str
    api_path: str
    cells: list[NotebookCell] = field(default_factory=list)
    example_type: str = "notebook"
    track_info: VariableTrack | None = None


class NotebookExampleExtractor:
    """Extracts usage examples from Jupyter notebooks."""

    def __init__(
        self,
        repo_path: str,
        api_elements: set[str],
        max_output_lines: int = 10,
        max_markdown_lines: int = 10,
    ):
        """Initialize the notebook example extractor.

        Args:
            repo_path: Path to the repository root
            api_elements: Set of known API elements to track (fully qualified names)
            max_output_lines: Maximum lines of cell output to include
            max_markdown_lines: Maximum lines of markdown cell to include
        """
        self.repo_path = Path(repo_path)
        self.api_elements = api_elements
        self.max_output_lines = max_output_lines
        self.max_markdown_lines = max_markdown_lines
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

    def extract_from_notebook(self, notebook_path: str) -> list[NotebookExample]:
        """Extract examples from a single Jupyter notebook."""
        with open(notebook_path, encoding="utf-8") as f:
            notebook_data = json.load(f)

        cells = self._parse_notebook_cells(notebook_data)
        imports = self._extract_imports(cells)
        tracks = self._track_variable_usage(cells, imports)
        examples = self._build_examples(notebook_path, cells, tracks)

        return examples

    def extract_from_notebooks(self, notebook_paths: list[str]) -> list[NotebookExample]:
        """Extract examples from multiple Jupyter notebooks."""
        all_examples: list[NotebookExample] = []

        for notebook_path in notebook_paths:
            try:
                all_examples.extend(self.extract_from_notebook(notebook_path))
            except Exception:
                continue

        return all_examples

    def _parse_notebook_cells(self, notebook_data: dict[str, Any]) -> list[NotebookCell]:
        """Parse notebook cells into NotebookCell objects."""
        cells: list[NotebookCell] = []

        for idx, cell_data in enumerate(notebook_data.get("cells", [])):
            cell_type = cell_data.get("cell_type", "")

            source = cell_data.get("source", [])
            if isinstance(source, list):
                source = "".join(source)

            outputs: list[str] = []
            if cell_type == "code":
                for output in cell_data.get("outputs", []):
                    output_text = self._extract_output_text(output)
                    if output_text:
                        outputs.append(output_text)

            execution_count = cell_data.get("execution_count")

            cell = NotebookCell(
                cell_type=cell_type,
                index=idx,
                source=source,
                outputs=outputs,
                execution_count=execution_count,
            )
            cells.append(cell)

        return cells

    def _extract_output_text(self, output: dict[str, Any]) -> str:
        """Extract text from a cell output."""
        output_type = output.get("output_type", "")
        text_parts: list[str] = []

        if output_type == "stream":
            text = output.get("text", [])
            text_parts.append("".join(text) if isinstance(text, list) else text)

        elif output_type in ("execute_result", "display_data"):
            data = output.get("data", {})
            if "text/plain" in data:
                text = data["text/plain"]
                text_parts.append("".join(text) if isinstance(text, list) else text)

        elif output_type == "error":
            text_parts.append(f"Error: {output.get('ename', '')}: {output.get('evalue', '')}")

        full_text = "\n".join(text_parts)
        lines = full_text.split("\n")

        if len(lines) > self.max_output_lines:
            truncated_lines = lines[: self.max_output_lines]
            truncated_lines.append(f"... (truncated, {len(lines) - self.max_output_lines} more lines)")
            return "\n".join(truncated_lines)

        return full_text

    def _strip_magic_commands(self, source: str) -> str:
        """Strip Jupyter magic commands from source code."""
        return "\n".join(line for line in source.split("\n") if not line.strip().startswith(("%", "%%")))

    def _extract_imports(self, cells: list[NotebookCell]) -> dict[str, dict[str, Any]]:
        """Extract import statements from notebook cells."""
        imports: dict[str, dict[str, Any]] = {}

        for cell in cells:
            if cell.cell_type != "code":
                continue

            try:
                cleaned_source = self._strip_magic_commands(cell.source)
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=SyntaxWarning)
                    tree = ast.parse(cleaned_source)

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            name = alias.asname if alias.asname else alias.name
                            imports[name] = {
                                "module": alias.name,
                                "cell_idx": cell.index,
                            }

                    elif isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        for alias in node.names:
                            name = alias.asname if alias.asname else alias.name
                            imports[name] = {
                                "module": module,
                                "from_import": alias.name,
                                "cell_idx": cell.index,
                            }

            except SyntaxError:
                continue

        return imports

    def _track_variable_usage(
        self, cells: list[NotebookCell], imports: dict[str, dict[str, Any]]
    ) -> list[VariableTrack]:
        """Track variable initialization and usage across cells."""
        tracks: list[VariableTrack] = []
        variable_to_api: dict[str, tuple[str, VariableTrack]] = {}

        for cell in cells:
            if cell.cell_type != "code":
                continue

            try:
                cleaned_source = self._strip_magic_commands(cell.source)
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=SyntaxWarning)
                    tree = ast.parse(cleaned_source)

                for node in ast.walk(tree):
                    if isinstance(node, ast.Assign):
                        api_info = self._identify_api_call(node.value, imports)

                        if api_info and api_info["api_path"] in self.api_elements:
                            for target in node.targets:
                                if isinstance(target, ast.Name):
                                    var_name = target.id
                                    is_direct = self._is_direct_usage(node.value)
                                    import_cell_idx = api_info.get("import_cell_idx", cell.index)

                                    track = VariableTrack(
                                        api_path=api_info["api_path"],
                                        variable_name=var_name,
                                        import_cell_idx=import_cell_idx,
                                        init_cell_idx=cell.index,
                                        is_direct_usage=is_direct,
                                    )

                                    if not is_direct:
                                        variable_to_api[var_name] = (
                                            api_info["api_path"],
                                            track,
                                        )

                                    tracks.append(track)

                    elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                        api_info = self._identify_api_call(node.value, imports)

                        if api_info and api_info["api_path"] in self.api_elements:
                            import_cell_idx = api_info.get("import_cell_idx", cell.index)
                            var_name = f"_standalone_call_{cell.index}"

                            track = VariableTrack(
                                api_path=api_info["api_path"],
                                variable_name=var_name,
                                import_cell_idx=import_cell_idx,
                                init_cell_idx=cell.index,
                                is_direct_usage=True,
                            )

                            tracks.append(track)

            except SyntaxError:
                continue

        # Second pass: find variable references
        for cell in cells:
            if cell.cell_type != "code":
                continue

            for var_name, (_, track) in variable_to_api.items():
                if cell.index > track.init_cell_idx and self._cell_references_variable(cell.source, var_name):
                    track.usage_cell_indices.add(cell.index)

        return tracks

    def _identify_api_call(self, node: ast.AST, imports: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
        """Identify if an AST node is a call to a known API element."""
        if not isinstance(node, ast.Call):
            return None

        func = node.func

        if isinstance(func, ast.Name):
            name = func.id
            if name in imports:
                import_info = imports[name]
                module = import_info.get("module", "")
                from_import = import_info.get("from_import", name)

                candidate_path = f"{module}.{from_import}" if module else from_import

                resolved_path = self._resolve_api_path(candidate_path)

                if resolved_path:
                    return {
                        "api_path": resolved_path,
                        "import_cell_idx": import_info.get("cell_idx", 0),
                    }

                if from_import and from_import != candidate_path:
                    resolved_path = self._resolve_api_path(from_import)
                    if resolved_path:
                        return {
                            "api_path": resolved_path,
                            "import_cell_idx": import_info.get("cell_idx", 0),
                        }

                if candidate_path in self.api_elements:
                    return {
                        "api_path": candidate_path,
                        "import_cell_idx": import_info.get("cell_idx", 0),
                    }

        elif isinstance(func, ast.Attribute):
            parts: list[str] = []
            current: ast.expr = func

            while isinstance(current, ast.Attribute):
                parts.insert(0, current.attr)
                current = current.value

            if isinstance(current, ast.Name):
                parts.insert(0, current.id)

            if parts and parts[0] in imports:
                import_info = imports[parts[0]]
                module = import_info.get("module", parts[0])
                candidate_path = module + "." + ".".join(parts[1:])
                resolved_path = self._resolve_api_path(candidate_path)

                if resolved_path:
                    return {
                        "api_path": resolved_path,
                        "import_cell_idx": import_info.get("cell_idx", 0),
                    }

                if candidate_path in self.api_elements:
                    return {
                        "api_path": candidate_path,
                        "import_cell_idx": import_info.get("cell_idx", 0),
                    }

        return None

    def _is_direct_usage(self, node: ast.AST) -> bool:
        """Check if a Call node represents direct usage."""
        if not isinstance(node, ast.Call):
            return False
        return isinstance(node.func, ast.Attribute)

    def _cell_references_variable(self, source: str, var_name: str) -> bool:
        """Check if a cell's source code references a variable."""
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=SyntaxWarning)
                tree = ast.parse(source)

            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id == var_name:
                    return True

                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == var_name:
                    return True

        except SyntaxError:
            pattern = r"\b" + re.escape(var_name) + r"\b"
            return bool(re.search(pattern, source))

        return False

    def _build_examples(
        self,
        notebook_path: str,
        cells: list[NotebookCell],
        tracks: list[VariableTrack],
    ) -> list[NotebookExample]:
        """Build NotebookExample objects from variable tracks."""
        examples: list[NotebookExample] = []

        for track in tracks:
            cell_indices = {track.import_cell_idx, track.init_cell_idx}
            if not track.is_direct_usage:
                cell_indices.update(track.usage_cell_indices)

            cell_indices = self._expand_with_markdown(cells, cell_indices)
            sorted_indices = sorted(cell_indices)
            example_cells = [cells[idx] for idx in sorted_indices]

            examples.append(
                NotebookExample(
                    source_file=notebook_path,
                    api_path=track.api_path,
                    cells=example_cells,
                    track_info=track,
                )
            )

        return examples

    def _expand_with_markdown(self, cells: list[NotebookCell], cell_indices: set[int]) -> set[int]:
        """Expand cell indices to include neighboring markdown cells."""
        expanded = set(cell_indices)

        for idx in list(cell_indices):
            prev_idx = idx - 1
            while prev_idx >= 0 and cells[prev_idx].cell_type == "markdown":
                expanded.add(prev_idx)
                prev_idx -= 1

            next_idx = idx + 1
            while next_idx < len(cells) and cells[next_idx].cell_type == "markdown":
                expanded.add(next_idx)
                break

        return expanded

    def format_example(self, example: NotebookExample, include_headers: bool = True) -> str:
        """Format a NotebookExample as a string for inclusion in documentation."""
        lines: list[str] = []

        if include_headers:
            lines.append(f"# From: {example.source_file}")
            if example.track_info:
                lines.append(f"# Variable: {example.track_info.variable_name}")
            lines.append("")

        for cell in example.cells:
            if cell.cell_type == "markdown":
                markdown_lines = cell.source.split("\n")

                if len(markdown_lines) > self.max_markdown_lines:
                    for line in markdown_lines[: self.max_markdown_lines]:
                        lines.append(f"# {line}")
                    lines.append(
                        f"# ... (markdown truncated, {len(markdown_lines) - self.max_markdown_lines} more lines)"
                    )
                else:
                    for line in markdown_lines:
                        lines.append(f"# {line}")
                lines.append("")

            elif cell.cell_type == "code":
                lines.append(cell.source)

                if cell.outputs:
                    lines.append("")
                    lines.append("# Output:")
                    for output in cell.outputs:
                        for line in output.split("\n"):
                            lines.append(f"# {line}")
                    lines.append("")

        return "\n".join(lines)


def extract_notebook_examples_from_repository(
    repo_path: str,
    api_elements: set[str],
    notebook_paths: list[str] | None = None,
    max_output_lines: int = 5,
    max_markdown_lines: int = 5,
) -> list[NotebookExample]:
    """Extract examples from notebooks in a repository.

    Args:
        repo_path: Path to the repository
        api_elements: Set of known API elements to track
        notebook_paths: Optional list of specific notebook paths.
                       If None, will search for all .ipynb files in repo.
        max_output_lines: Maximum lines of cell output to include
        max_markdown_lines: Maximum lines of markdown cell to include

    Returns:
        List of NotebookExample objects
    """
    extractor = NotebookExampleExtractor(repo_path, api_elements, max_output_lines, max_markdown_lines)

    if notebook_paths is None:
        repo_path_obj = Path(repo_path)
        notebook_paths = [str(p) for p in repo_path_obj.rglob("*.ipynb")]

    return extractor.extract_from_notebooks(notebook_paths)

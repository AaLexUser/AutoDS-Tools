"""Aggregate usage examples from tests, examples, markdown, and notebooks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pygrad.processor.example_extractor import (
    APIUsageGroup,
    ExampleExtractor,
    UsageExample,
    extract_examples_from_repository,
)
from pygrad.processor.markdown_extractor import extract_markdown_examples_from_repository
from pygrad.processor.notebook_extractor import extract_notebook_examples_from_repository
from pygrad.processor.utils import extract_test_example_paths


def _build_api_elements(project_structure: dict[str, Any], repo_path: Path) -> set[str]:
    """Build the public API surface used to link markdown and notebook examples."""
    paths = extract_test_example_paths(repo_path)
    exclusion_paths = set(paths["test"] + paths["example"])
    api_elements: set[str] = set()

    for file_path, file_structure in project_structure.items():
        if any(str(excl) in file_path for excl in exclusion_paths):
            continue
        stem = Path(file_path).stem
        if stem.startswith("_") and stem != "__init__":
            continue

        try:
            rel_path = Path(file_path).relative_to(repo_path)
            module_parts = [*list(rel_path.parts)[:-1], rel_path.stem]
            module_parts = [p for p in module_parts if p and p != "__init__"]
            module_path = ".".join(module_parts)
        except ValueError:
            module_path = ""

        for item in file_structure.get("structure", []):
            if item["type"] == "class":
                class_name = item["name"]
                if class_name.startswith("_"):
                    continue
                class_api_path = f"{module_path}.{class_name}" if module_path else class_name
                api_elements.add(class_api_path)
                for method in item.get("methods", []):
                    method_name = method["method_name"]
                    if not method_name.startswith("_") or method_name == "__init__":
                        api_elements.add(f"{class_api_path}.{method_name}")
            elif item["type"] == "function":
                function_name = item["details"]["method_name"]
                if not function_name.startswith("_"):
                    api_path = f"{module_path}.{function_name}" if module_path else function_name
                    api_elements.add(api_path)

    return api_elements


def _merge_usage_groups(
    base: dict[str, APIUsageGroup],
    extra_examples: list[UsageExample],
) -> dict[str, APIUsageGroup]:
    """Merge additional examples into grouped API usage."""
    for example in extra_examples:
        for api_path in example.used_api_elements:
            if api_path not in base:
                base[api_path] = APIUsageGroup(api_path=api_path, examples=[])
            base[api_path].examples.append(example)
            base[api_path].total_usage_count += 1
    return base


def extract_all_examples_from_repository(
    repo_path: str,
    project_structure: dict[str, Any] | None = None,
) -> dict[str, APIUsageGroup]:
    """Extract examples from tests, example dirs, README/docs markdown, and notebooks."""
    repo = Path(repo_path)
    grouped = extract_examples_from_repository(repo_path, project_structure)

    if project_structure is None:
        from pygrad.parser.treesitter import RepoTreeSitter

        project_structure = RepoTreeSitter(repo_path).analyze_directory(repo_path)

    api_elements = _build_api_elements(project_structure, repo)
    extra: list[UsageExample] = []

    readme = repo / "README.md"
    markdown_paths = [str(readme)] if readme.exists() else []
    docs_dir = repo / "docs"
    if docs_dir.exists():
        markdown_paths.extend(str(p) for p in docs_dir.rglob("*.md"))

    for md_example in extract_markdown_examples_from_repository(repo_path, api_elements, markdown_paths):
        extra.append(
            UsageExample(
                source_file=md_example.source_file,
                function_name=md_example.header or "readme",
                source_code=md_example.code,
                start_line=0,
                used_api_elements=md_example.api_paths,
                example_type=md_example.example_type,
                docstring=md_example.description,
                header=md_example.header,
            )
        )

    paths = extract_test_example_paths(repo)
    notebook_paths = [str(p) for p in repo.rglob("*.ipynb")]
    if paths["example"]:
        tutorial_notebooks = [p for p in notebook_paths if any(ex in p for ex in paths["example"])]
    else:
        tutorial_notebooks = notebook_paths

    notebook_extractor = extract_notebook_examples_from_repository(
        repo_path,
        api_elements,
        notebook_paths=tutorial_notebooks or notebook_paths,
        max_output_lines=5,
        max_markdown_lines=8,
    )
    from pygrad.processor.notebook_extractor import NotebookExampleExtractor

    formatter = NotebookExampleExtractor(repo_path, api_elements)
    for nb_example in notebook_extractor:
        source_code = formatter.format_example(nb_example, include_headers=True)
        extra.append(
            UsageExample(
                source_file=nb_example.source_file,
                function_name=Path(nb_example.source_file).stem,
                source_code=source_code,
                start_line=0,
                used_api_elements={nb_example.api_path},
                example_type="notebook",
                docstring=f"Notebook tutorial for {nb_example.api_path}",
                header=Path(nb_example.source_file).name,
            )
        )

    return _merge_usage_groups(grouped, extra)

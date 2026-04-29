"""Extract method-level usage examples from test and example codebases."""

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pygrad.parser.treesitter import RepoTreeSitter
from pygrad.processor.utils import extract_test_example_paths


@dataclass
class UsageExample:
    """Represents a single usage example extracted from tests or examples."""

    source_file: str
    function_name: str
    source_code: str
    start_line: int
    used_api_elements: set[str] = field(default_factory=set)
    example_type: str = "test"
    docstring: str | None = None
    header: str | None = None
    variable_name: str | None = None


@dataclass
class APIUsageGroup:
    """Groups examples by the API element they demonstrate."""

    api_path: str
    examples: list[UsageExample] = field(default_factory=list)
    total_usage_count: int = 0


class ExampleExtractor:
    """Extracts method-level usage examples from test and example codebases."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.treesitter = RepoTreeSitter(str(self.repo_path))
        self.api_elements: set[str] = set()
        self.module_map: dict[str, str] = {}

    def extract_examples(
        self,
        project_structure: dict[str, Any],
        test_paths: list[str],
        example_paths: list[str],
    ) -> dict[str, APIUsageGroup]:
        """Extract usage examples from test and example directories."""
        self._build_api_surface(project_structure, test_paths, example_paths)
        test_examples = self._extract_from_tests(test_paths)
        example_examples = self._extract_from_examples(example_paths)
        return self._group_by_api_element(test_examples + example_examples)

    def _build_api_surface(
        self,
        project_structure: dict[str, Any],
        test_paths: list[str],
        example_paths: list[str],
    ) -> None:
        """Build a map of the public API surface."""
        exclusion_paths = set(test_paths + example_paths)

        for file_path, file_structure in project_structure.items():
            if any(str(excl) in file_path for excl in exclusion_paths):
                continue
            stem = Path(file_path).stem
            if stem.startswith("_") and stem != "__init__":
                continue

            module_path = self._get_module_path(file_path)
            self.module_map[module_path] = file_path

            for item in file_structure.get("structure", []):
                if item["type"] == "class":
                    class_name = item["name"]
                    if class_name.startswith("_"):
                        continue
                    class_api_path = f"{module_path}.{class_name}" if module_path else class_name
                    self.api_elements.add(class_api_path)

                    for method in item.get("methods", []):
                        method_name = method["method_name"]
                        if not method_name.startswith("_") or method_name == "__init__":
                            self.api_elements.add(f"{class_api_path}.{method_name}")

                elif item["type"] == "function":
                    function_name = item["details"]["method_name"]
                    if not function_name.startswith("_"):
                        api_path = f"{module_path}.{function_name}" if module_path else function_name
                        self.api_elements.add(api_path)

    def _extract_from_tests(self, test_paths: list[str]) -> list[UsageExample]:
        """Extract examples from test files."""
        examples = []
        for test_path in test_paths:
            if not Path(test_path).exists():
                continue
            test_structure = self.treesitter.analyze_directory(test_path)

            for file_path, file_structure in test_structure.items():
                for item in file_structure.get("structure", []):
                    if item["type"] == "function":
                        details = item["details"]
                        if not details["method_name"].startswith("test_"):
                            continue
                        source_code = details.get("source_code", "")
                        examples.append(
                            UsageExample(
                                source_file=file_path,
                                function_name=details["method_name"],
                                source_code=source_code,
                                start_line=details.get("start_line", 0),
                                used_api_elements=self._find_used_api_elements(source_code),
                                example_type="test",
                                docstring=details.get("docstring"),
                            )
                        )
                    elif item["type"] == "class":
                        for method in item.get("methods", []):
                            if not method["method_name"].startswith("test_"):
                                continue
                            source_code = method.get("source_code", "")
                            examples.append(
                                UsageExample(
                                    source_file=file_path,
                                    function_name=f"{item['name']}.{method['method_name']}",
                                    source_code=source_code,
                                    start_line=method.get("start_line", 0),
                                    used_api_elements=self._find_used_api_elements(source_code),
                                    example_type="test",
                                    docstring=method.get("docstring"),
                                )
                            )
        return examples

    def _extract_from_examples(self, example_paths: list[str]) -> list[UsageExample]:
        """Extract examples from example codebases."""
        examples = []
        for example_path in example_paths:
            if not Path(example_path).exists():
                continue
            example_structure = self.treesitter.analyze_directory(example_path)

            for file_path, file_structure in example_structure.items():
                for item in file_structure.get("structure", []):
                    if item["type"] == "function":
                        details = item["details"]
                        if details["method_name"].startswith("_"):
                            continue
                        source_code = details.get("source_code", "")
                        examples.append(
                            UsageExample(
                                source_file=file_path,
                                function_name=details["method_name"],
                                source_code=source_code,
                                start_line=details.get("start_line", 0),
                                used_api_elements=self._find_used_api_elements(source_code),
                                example_type="example",
                                docstring=details.get("docstring"),
                            )
                        )
        return examples

    def _group_by_api_element(self, examples: list[UsageExample]) -> dict[str, APIUsageGroup]:
        """Group examples by API elements they demonstrate."""
        grouped: dict[str, APIUsageGroup] = defaultdict(lambda: APIUsageGroup(api_path="", examples=[]))
        for example in examples:
            for api_path in example.used_api_elements:
                if api_path not in grouped:
                    grouped[api_path] = APIUsageGroup(api_path=api_path, examples=[])
                grouped[api_path].examples.append(example)
                grouped[api_path].total_usage_count += 1
        return dict(grouped)

    def _find_used_api_elements(self, source_code: str) -> set[str]:
        """Find which API elements are used in the source code."""
        used_elements = set()

        # Check each API element to see if it appears in the source code
        for api_path in self.api_elements:
            # Split api_path to check for both full path and simple name
            parts = api_path.split(".")

            # Check if the full API path appears (e.g., "module.ClassName.method_name")
            if api_path in source_code:
                used_elements.add(api_path)
                continue

            # Check if class name appears (for imports like "from module import ClassName")
            if len(parts) >= 2:
                class_or_func_name = parts[-1]
                if class_or_func_name in source_code:
                    used_elements.add(api_path)

        return used_elements

    def _get_module_path(self, file_path: str) -> str:
        """Generate module path from file path."""
        try:
            rel_path = Path(file_path).relative_to(self.repo_path)
            module_parts = [*list(rel_path.parts)[:-1], rel_path.stem]
            module_parts = [p for p in module_parts if p and p != "__init__"]
            return ".".join(module_parts)
        except (ValueError, AttributeError):
            return ""


def extract_examples_from_repository(
    repo_path: str, project_structure: dict[str, Any] | None = None
) -> dict[str, APIUsageGroup]:
    """Convenience function to extract examples from a repository."""
    extractor = ExampleExtractor(repo_path)
    paths = extract_test_example_paths(Path(repo_path))

    if project_structure is None:
        treesitter = RepoTreeSitter(repo_path)
        project_structure = treesitter.analyze_directory(repo_path)

    return extractor.extract_examples(project_structure, paths["test"], paths["example"])

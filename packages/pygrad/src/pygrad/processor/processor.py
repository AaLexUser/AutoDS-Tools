"""Python Repository Processor for generating LLM-ready API documentation."""

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.dom import minidom

from pygrad.parser.treesitter import RepoTreeSitter
from pygrad.processor.example_extractor import extract_examples_from_repository
from pygrad.processor.neo4j_graph import Neo4jGraphConverter
from pygrad.processor.utils import extract_important_api, extract_test_example_paths


@dataclass
class FunctionInfo:
    """Information about a function or method."""

    name: str
    api_path: str
    description: str
    header: str
    output: str
    usage_examples: list[str]


@dataclass
class ClassInfo:
    """Information about a class."""

    name: str
    api_path: str
    description: str
    initialization: dict[str, str]
    methods: list[FunctionInfo]
    usage_examples: list[str]


async def process_repository(
    repository_path: str,
    output_file: str = "api.xml",
    top_n: int = 15,
) -> str:
    """Process repository and generate API documentation.

    Args:
        repository_path: Path to the repository
        output_file: Output XML filename
        top_n: Number of top important files to include

    Returns:
        Formatted result string with file paths
    """
    repo_path = Path(repository_path)
    if not repo_path.exists():
        raise RuntimeError(f"Repository path {repository_path} does not exist")

    important_files = extract_important_api(repo_path, top_n=top_n)
    if not important_files:
        raise RuntimeError("No important files found in the repository")

    processor = PythonRepositoryProcessor(str(repo_path))
    classes, functions = processor.process_repository_data()

    api_usage_groups = extract_examples_from_repository(str(repo_path), processor.analysis_results)
    processor._merge_examples_into_data(classes, functions, api_usage_groups)

    output_path = processor.save_repository_data(classes, functions, important_files, output_file)

    result = f"Repository: {repository_path}\n"
    result += f"Important files: {len(important_files)}\n"
    result += f"Output saved to: {output_path}\n"
    return result


async def process_repository_to_neo4j(
    repository_path: str,
    neo4j_uri: str,
    neo4j_username: str,
    neo4j_password: str,
    repository_id: str,
    database: str = "neo4j",
    clear_existing: bool = False,
) -> dict[str, int]:
    """Process repository and save directly to Neo4j graph database.

    Args:
        repository_path: Path to the repository
        neo4j_uri: Neo4j connection URI (e.g., "bolt://localhost:7687")
        neo4j_username: Neo4j username
        neo4j_password: Neo4j password
        repository_id: Repository identifier for node isolation
        database: Database name (default: "neo4j")
        clear_existing: Whether to clear existing graph data for this repository

    Returns:
        Dictionary with counts of created nodes and relationships
    """
    repo_path = Path(repository_path)
    if not repo_path.exists():
        raise RuntimeError(f"Repository path {repository_path} does not exist")

    processor = PythonRepositoryProcessor(str(repo_path))
    classes, functions = processor.process_repository_data()

    api_usage_groups = extract_examples_from_repository(str(repo_path), processor.analysis_results)
    processor._merge_examples_into_data(classes, functions, api_usage_groups)

    stats = processor.save_repository_to_neo4j(
        classes,
        functions,
        neo4j_uri,
        neo4j_username,
        neo4j_password,
        repository_id,
        database,
        clear_existing,
    )

    return stats


class PythonRepositoryProcessor:
    """Processes Python repositories to generate LLM-ready API documentation."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.treesitter = RepoTreeSitter(str(self.repo_path))
        self.analysis_results: dict[str, Any] = {}

    def process_repository_data(self) -> tuple[list[ClassInfo], list[FunctionInfo]]:
        """Process repository and return structured data."""
        self.analysis_results = self.treesitter.analyze_directory(str(self.repo_path))
        classes, functions = self._process_analysis_results(self.analysis_results)

        # Exclude test and example dirs
        paths = extract_test_example_paths(self.repo_path)
        exclusions = [Path(p).relative_to(self.repo_path) for p in paths["test"] + paths["example"]]

        def is_excluded(api_path: str) -> bool:
            p = Path(api_path.replace(".", "/"))
            return any(p == exc or exc in p.parents for exc in exclusions)

        classes = [c for c in classes if not is_excluded(c.api_path)]
        functions = [f for f in functions if not is_excluded(f.api_path)]
        return classes, functions

    def save_repository_data(
        self,
        classes: list[ClassInfo],
        functions: list[FunctionInfo],
        important_files: list[tuple[str, float]],
        output_file: str = "api.xml",
    ) -> str:
        """Save processed data to XML file."""
        xml_content = self._generate_xml(classes, functions, important_files)
        output_path = self.repo_path / output_file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(xml_content)
        return str(output_path)

    def save_repository_to_neo4j(
        self,
        classes: list[ClassInfo],
        functions: list[FunctionInfo],
        neo4j_uri: str,
        neo4j_username: str,
        neo4j_password: str,
        repository_id: str,
        database: str = "neo4j",
        clear_existing: bool = False,
    ) -> dict[str, int]:
        """Save processed data to Neo4j graph database.

        Args:
            classes: List of class information
            functions: List of function information
            neo4j_uri: Neo4j connection URI (e.g., "bolt://localhost:7687")
            neo4j_username: Neo4j username
            neo4j_password: Neo4j password
            repository_id: Repository identifier for node isolation
            database: Database name (default: "neo4j")
            clear_existing: Whether to clear existing graph data for this repository

        Returns:
            Dictionary with counts of created nodes and relationships
        """
        with Neo4jGraphConverter(neo4j_uri, neo4j_username, neo4j_password, database) as converter:
            return converter.save_repository_graph(classes, functions, repository_id, clear_existing)

    def _process_analysis_results(self, analysis_results: dict[str, Any]) -> tuple[list[ClassInfo], list[FunctionInfo]]:
        """Process tree-sitter results into structured data."""
        classes = []
        functions = []

        for filename, file_structure in analysis_results.items():
            module_path = self._get_module_path(filename)

            for item in file_structure.get("structure", []):
                if item["type"] == "class":
                    classes.append(self._process_class(item, module_path))
                elif item["type"] == "function":
                    func_name = item["details"]["method_name"]
                    if not func_name.startswith("_"):
                        functions.append(self._process_function(item["details"], module_path))

        return classes, functions

    def _get_module_path(self, filename: str) -> str:
        """Generate module path from filename."""
        rel_path = Path(filename).relative_to(self.repo_path)
        module_parts = [*list(rel_path.parts)[:-1], rel_path.stem]
        module_parts = [p for p in module_parts if p and p != "__init__"]
        return ".".join(module_parts)

    def _process_class(self, class_item: dict[str, Any], module_path: str) -> ClassInfo:
        """Process a class from tree-sitter analysis."""
        class_name = class_item["name"]
        api_path = f"{module_path}.{class_name}" if module_path else class_name
        description = self._clean_docstring(class_item.get("docstring", ""))

        init_method = next(
            (m for m in class_item.get("methods", []) if m["method_name"] == "__init__"),
            None,
        )

        initialization = {
            "parameters": ", ".join(init_method["arguments"] if init_method else []),
            "description": self._clean_docstring(init_method["docstring"] if init_method else ""),
        }

        methods = [
            self._process_method(method, api_path)
            for method in class_item.get("methods", [])
            if method["method_name"] != "__init__" and not method["method_name"].startswith("_")
        ]

        return ClassInfo(
            name=class_name,
            api_path=api_path,
            description=description,
            initialization=initialization,
            methods=methods,
            usage_examples=[],
        )

    def _process_function(self, func_item: dict[str, Any], module_path: str) -> FunctionInfo:
        """Process a function from tree-sitter analysis."""
        name = func_item["method_name"]
        api_path = f"{module_path}.{name}" if module_path else name
        description = self._clean_docstring(func_item.get("docstring", ""))
        params = ", ".join(func_item.get("arguments", []))
        return_type = func_item.get("return_type", "")
        header = f"def {name}({params})"
        if return_type:
            header += f" -> {return_type}"

        return FunctionInfo(
            name=name,
            api_path=api_path,
            description=description,
            header=header,
            output="",
            usage_examples=[],
        )

    def _process_method(self, method_item: dict[str, Any], class_api_path: str) -> FunctionInfo:
        """Process a method from tree-sitter analysis."""
        name = method_item["method_name"]
        api_path = f"{class_api_path}.{name}"
        description = self._clean_docstring(method_item.get("docstring", ""))
        params = ", ".join(method_item.get("arguments", []))
        return_type = method_item.get("return_type", "")
        header = f"def {name}({params})"
        if return_type:
            header += f" -> {return_type}"

        return FunctionInfo(
            name=name,
            api_path=api_path,
            description=description,
            header=header,
            output="",
            usage_examples=[],
        )

    def _clean_docstring(self, docstring: str | None) -> str:
        """Clean and format docstring."""
        if not docstring:
            return ""
        cleaned = docstring.strip()
        for quote in ('"""', "'''"):
            cleaned = cleaned.removeprefix(quote).removesuffix(quote)
        return cleaned.strip()

    def _merge_examples_into_data(
        self,
        classes: list[ClassInfo],
        functions: list[FunctionInfo],
        api_usage_groups: dict[str, Any],
    ) -> None:
        """Merge extracted usage examples into class and function data."""
        for function in functions:
            if function.api_path in api_usage_groups:
                usage_group = api_usage_groups[function.api_path]
                function.usage_examples = [self._format_usage_example(ex) for ex in usage_group.examples]

        for class_info in classes:
            if class_info.api_path in api_usage_groups:
                usage_group = api_usage_groups[class_info.api_path]
                class_info.usage_examples = [self._format_usage_example(ex) for ex in usage_group.examples]
            for method in class_info.methods:
                if method.api_path in api_usage_groups:
                    usage_group = api_usage_groups[method.api_path]
                    method.usage_examples = [self._format_usage_example(ex) for ex in usage_group.examples]

    def _make_relative_path(self, path: str) -> str:
        """Convert an absolute path to a path relative to the repository root.

        Args:
            path: Absolute path to convert

        Returns:
            Path relative to repository root
        """
        try:
            path_obj = Path(path)
            # If path is already relative, return as is
            if not path_obj.is_absolute():
                return path
            # Convert to relative path from repo root
            rel_path = path_obj.relative_to(self.repo_path)
            return str(rel_path)
        except (ValueError, TypeError):
            # If conversion fails (path is outside repo), return as is
            return path

    def _format_usage_example(self, example: Any) -> str:
        """Format a UsageExample as JSON string."""
        return json.dumps(
            {
                "from": self._make_relative_path(example.source_file),
                "type": example.example_type,
                "line": example.start_line,
                "variable": getattr(example, "variable_name", None),
                "header": getattr(example, "header", None),
                "source_code": example.source_code,
            }
        )

    def _generate_xml(
        self,
        classes: list[ClassInfo],
        functions: list[FunctionInfo],
        important_files: list[tuple[str, float]],
    ) -> str:
        """Generate XML output."""
        root = ET.Element("repository")

        # Important files
        files_elem = ET.SubElement(root, "important_files")
        for file_path, score in important_files:
            file_elem = ET.SubElement(files_elem, "file")
            file_elem.set("score", str(round(score)))
            file_elem.text = self._make_relative_path(file_path)

        # Classes
        for cls in classes:
            cls_elem = ET.SubElement(root, "class")
            ET.SubElement(cls_elem, "name").text = cls.name
            ET.SubElement(cls_elem, "api_path").text = cls.api_path
            ET.SubElement(cls_elem, "description").text = cls.description

            init_elem = ET.SubElement(cls_elem, "initialization")
            ET.SubElement(init_elem, "parameters").text = cls.initialization["parameters"]
            ET.SubElement(init_elem, "description").text = cls.initialization["description"]

            methods_elem = ET.SubElement(cls_elem, "methods")
            for method in cls.methods:
                self._add_function_to_xml(methods_elem, method, "method")

            self._add_examples_to_xml(cls_elem, cls.usage_examples)

        # Functions
        for func in functions:
            self._add_function_to_xml(root, func, "function")

        return self._prettify_xml(ET.tostring(root, encoding="unicode"))

    def _add_function_to_xml(self, parent: ET.Element, func: FunctionInfo, tag: str) -> None:
        """Add function/method to XML."""
        elem = ET.SubElement(parent, tag)
        ET.SubElement(elem, "name").text = func.name
        ET.SubElement(elem, "api_path").text = func.api_path
        ET.SubElement(elem, "description").text = func.description
        ET.SubElement(elem, "header").text = func.header
        ET.SubElement(elem, "output").text = func.output
        self._add_examples_to_xml(elem, func.usage_examples)

    def _add_examples_to_xml(self, parent: ET.Element, examples: list[str]) -> None:
        """Add usage examples to XML element."""
        examples_elem = ET.SubElement(parent, "usage_examples")
        for example in examples:
            example_elem = ET.SubElement(examples_elem, "example")
            try:
                data = json.loads(example)
                for key in ("from", "type", "line", "variable", "header"):
                    if data.get(key) is not None:
                        ET.SubElement(example_elem, key).text = str(data[key])
                ET.SubElement(example_elem, "source_code").text = data.get("source_code", "")
            except (json.JSONDecodeError, TypeError):
                example_elem.text = example

    def _prettify_xml(self, xml_string: str) -> str:
        """Prettify XML string."""
        # Remove control characters
        xml_string = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", xml_string)
        try:
            dom = minidom.parseString(xml_string)
            return dom.toprettyxml(indent="  ", encoding=None)
        except Exception:
            return xml_string

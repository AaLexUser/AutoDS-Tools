"""Python source code AST parser using tree-sitter."""

import os
from typing import Any

import tree_sitter
import tree_sitter_python as tspython
from tree_sitter import Language, Parser


class RepoTreeSitter:
    """Extract Python source code structure for processing by LLM."""

    def __init__(self, scripts_path: str):
        """Initialize with path to Python scripts.

        Args:
            scripts_path: Path to directory containing Python files
        """
        self.cwd = scripts_path
        self.import_map: dict[str, str] = {}

    @staticmethod
    def files_list(path: str) -> tuple[list[str], bool]:
        """Get list of Python files in path.

        Returns:
            Tuple of (file_list, is_single_file)
        """
        if os.path.isdir(path):
            script_files = []
            for root, _, files in os.walk(path):
                for file in files:
                    if file.endswith(".py"):
                        script_files.append(os.path.join(root, file))
            return script_files, False
        elif os.path.isfile(path) and path.endswith(".py"):
            return [os.path.abspath(path)], True
        return [], False

    @staticmethod
    def open_file(file: str) -> str:
        """Read file contents."""
        with open(file, encoding="utf-8") as f:
            return f.read()

    def _build_parser(self) -> Parser:
        """Build Python parser."""
        return Parser(Language(tspython.language()))

    def _parse_source_code(self, filename: str) -> tuple[tree_sitter.Tree, str]:
        """Parse source code file."""
        parser = self._build_parser()
        source_code = self.open_file(filename)
        return parser.parse(source_code.encode("utf-8")), source_code

    def _get_docstring(self, block_node: tree_sitter.Node) -> str | None:
        """Extract docstring from block node."""
        for child in block_node.children:
            if child.type == "expression_statement":
                for c_c in child.children:
                    if c_c.type == "string":
                        return c_c.text.decode("utf-8") if c_c.text else None
        return None

    def _get_decorators(self, dec_list: list[str], dec_node: tree_sitter.Node) -> list[str]:
        """Extract decorators from node."""
        for decorator in dec_node.children:
            if decorator.type in ("identifier", "call") and decorator.text:
                dec_list.append(f"@{decorator.text.decode('utf-8')}")
        return dec_list

    def _get_attributes(self, class_attributes: list[str], block_node: tree_sitter.Node) -> list[str]:
        """Get class attributes from block."""
        for node in block_node.children:
            if node.type == "expression_statement":
                for child in node.children:
                    if child.type == "assignment":
                        for c in child.children:
                            if c.type == "identifier" and c.text:
                                class_attributes.append(c.text.decode("utf-8"))
        return class_attributes

    def _resolve_import_path(self, import_text: str, current_file: str | None = None) -> dict[str, Any]:
        """Resolve import path from import statement."""
        import_mapping: dict[str, Any] = {}

        if "import " not in import_text and "from " not in import_text:
            return import_mapping

        import_text = import_text.strip()

        if import_text.startswith("from"):
            try:
                from_part, import_part = import_text.split("import", 1)
            except ValueError:
                return import_mapping

            module_name = from_part.replace("from", "").strip()
            imported_entities = [entity.strip() for entity in import_part.split(",")]

            module_path = self._find_module_path(module_name, current_file)

            for entity in imported_entities:
                if " as " in entity:
                    imported_name, alias_name = [e.strip() for e in entity.split(" as ", 1)]
                else:
                    imported_name = entity
                    alias_name = imported_name

                if module_path:
                    import_mapping[alias_name] = {
                        "module": module_name,
                        "class": imported_name,
                        "path": module_path,
                    }

        elif import_text.startswith("import"):
            parts = import_text.replace("import", "").strip().split()
            if "as" in parts:
                idx = parts.index("as")
                module_name = parts[0]
                alias_name = parts[idx + 1]
            else:
                module_name = parts[0]
                alias_name = module_name

            module_path = self._find_module_path(module_name, None)
            if module_path:
                import_mapping[alias_name] = {
                    "module": module_name,
                    "path": module_path,
                }

        return import_mapping

    def _find_module_path(self, module_name: str, current_file: str | None) -> str | None:
        """Find the file path for a module."""
        if module_name.startswith(".") and current_file:
            level = len(module_name) - len(module_name.lstrip("."))
            remaining = module_name.lstrip(".")
            base_dir = os.path.dirname(os.path.abspath(current_file))
            for _ in range(level - 1):
                base_dir = os.path.dirname(base_dir)
            if remaining:
                path = os.path.join(base_dir, *remaining.split(".")) + ".py"
            else:
                path = os.path.join(base_dir, "__init__.py")
            return path if os.path.exists(path) else None
        else:
            path = os.path.join(self.cwd, *module_name.split(".")) + ".py"
            if os.path.exists(path):
                return path
            pkg_path = os.path.join(self.cwd, *module_name.split("."), "__init__.py")
            return pkg_path if os.path.exists(pkg_path) else None

    def _extract_imports(self, root_node: tree_sitter.Node, current_file: str | None = None) -> dict[str, Any]:
        """Extract imports from AST root."""
        import_map: dict[str, Any] = {}
        for node in root_node.children:
            if node.type in ("import_statement", "import_from_statement") and node.text:
                import_text = node.text.decode("utf-8")
                resolved = self._resolve_import_path(import_text, current_file)
                import_map.update(resolved)
        return import_map

    def _extract_function_details(
        self,
        function_node: tree_sitter.Node,
        source_code: str,
        imports: dict[str, Any],
        dec_list: list[str] | None = None,
    ) -> dict[str, Any]:
        """Extract details from a function definition."""
        if dec_list is None:
            dec_list = []

        name_node = function_node.child_by_field_name("name")
        method_name = name_node.text.decode("utf-8") if name_node and name_node.text else "unknown"
        start_line = function_node.start_point[0] + 1

        docstring = None
        for node in function_node.children:
            if node.type == "block":
                docstring = self._get_docstring(node)

        # Extract parameters
        params_node = function_node.child_by_field_name("parameters")
        arguments = []
        if params_node:
            for param_node in params_node.children:
                if param_node.type in ("typed_parameter", "typed_default_parameter"):
                    for child in param_node.children:
                        if child.type == "identifier" and child.text:
                            arguments.append(child.text.decode("utf-8"))
                elif param_node.type == "identifier" and param_node.text:
                    arguments.append(param_node.text.decode("utf-8"))

        source_bytes = source_code.encode("utf-8")
        source = source_bytes[function_node.start_byte : function_node.end_byte].decode("utf-8")

        return_node = function_node.child_by_field_name("return_type")
        return_type = None
        if return_node:
            return_type = source_code[return_node.start_byte : return_node.end_byte]

        return {
            "method_name": method_name,
            "decorators": dec_list,
            "docstring": docstring,
            "arguments": arguments,
            "return_type": return_type,
            "start_line": start_line,
            "source_code": source,
            "method_calls": [],
        }

    def _traverse_block(
        self, block_node: tree_sitter.Node, source_code: str, imports: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Traverse block to extract method definitions."""
        methods = []
        for child in block_node.children:
            if child.type == "decorated_definition":
                dec_list: list[str] = []
                for dec_child in child.children:
                    if dec_child.type == "decorator":
                        dec_list = self._get_decorators(dec_list, dec_child)
                    elif dec_child.type == "function_definition":
                        methods.append(self._extract_function_details(dec_child, source_code, imports, dec_list))
            elif child.type == "function_definition":
                methods.append(self._extract_function_details(child, source_code, imports))
        return methods

    def _class_parser(
        self,
        structure: dict[str, Any],
        source_code: str,
        node: tree_sitter.Node,
        dec_list: list[str] | None = None,
    ) -> None:
        """Parse class definition."""
        if dec_list is None:
            dec_list = []

        name_node = node.child_by_field_name("name")
        class_name = name_node.text.decode("utf-8") if name_node and name_node.text else "Unknown"
        start_line = node.start_point[0] + 1
        class_methods: list[dict[str, Any]] = []
        class_attributes: list[str] = []
        docstring = None

        for child in node.children:
            if child.type == "block":
                class_attributes = self._get_attributes(class_attributes, child)
                docstring = self._get_docstring(child)
                class_methods.extend(self._traverse_block(child, source_code, structure["imports"]))
            elif child.type == "function_definition":
                class_methods.append(self._extract_function_details(child, source_code, structure["imports"]))

        structure["structure"].append(
            {
                "type": "class",
                "name": class_name,
                "decorators": dec_list,
                "start_line": start_line,
                "docstring": docstring,
                "attributes": class_attributes,
                "methods": class_methods,
            }
        )

    def _function_parser(
        self,
        structure: dict[str, Any],
        source_code: str,
        node: tree_sitter.Node,
        dec_list: list[str] | None = None,
    ) -> None:
        """Parse function definition."""
        if dec_list is None:
            dec_list = []
        method_details = self._extract_function_details(node, source_code, structure["imports"], dec_list)
        structure["structure"].append(
            {
                "type": "function",
                "start_line": node.start_point[0] + 1,
                "details": method_details,
            }
        )

    def extract_structure(self, filename: str) -> dict[str, Any]:
        """Extract structure from a Python file."""
        structure: dict[str, Any] = {"structure": [], "imports": {}}
        tree, source_code = self._parse_source_code(filename)
        root_node = tree.root_node
        structure["imports"] = self._extract_imports(root_node, filename)

        for node in root_node.children:
            if node.type == "decorated_definition":
                dec_list: list[str] = []
                for dec_node in node.children:
                    if dec_node.type == "decorator":
                        dec_list = self._get_decorators(dec_list, dec_node)
                    elif dec_node.type == "class_definition":
                        self._class_parser(structure, source_code, dec_node, dec_list)
                    elif dec_node.type == "function_definition":
                        self._function_parser(structure, source_code, dec_node, dec_list)
            elif node.type == "function_definition":
                self._function_parser(structure, source_code, node)
            elif node.type == "class_definition":
                self._class_parser(structure, source_code, node)

        return structure

    def analyze_directory(self, path: str) -> dict[str, dict[str, Any]]:
        """Analyze all Python files in directory.

        Returns:
            Dictionary mapping filenames to their parsed structure
        """
        results: dict[str, dict[str, Any]] = {}
        files_list, is_single_file = self.files_list(path)

        if is_single_file:
            self.cwd = os.path.dirname(path)

        for filename in files_list:
            if filename.endswith(".py"):
                results[filename] = self.extract_structure(filename)

        return results

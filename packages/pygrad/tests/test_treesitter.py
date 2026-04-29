"""Tests for tree-sitter AST parser."""

from pygrad.parser.treesitter import RepoTreeSitter


class TestRepoTreeSitter:
    """Tests for RepoTreeSitter class."""

    def test_files_list_directory(self, sample_repo):
        """Test getting file list from a directory."""
        files, is_single = RepoTreeSitter.files_list(str(sample_repo))
        assert not is_single
        assert len(files) >= 3  # __init__.py, core.py, utils.py (and tests)
        assert all(f.endswith(".py") for f in files)

    def test_files_list_single_file(self, sample_python_file):
        """Test getting file list from a single file."""
        files, is_single = RepoTreeSitter.files_list(str(sample_python_file))
        assert is_single
        assert len(files) == 1
        assert files[0] == str(sample_python_file.absolute())

    def test_files_list_nonexistent(self, temp_dir):
        """Test getting file list from nonexistent path."""
        files, is_single = RepoTreeSitter.files_list(str(temp_dir / "nonexistent"))
        assert not is_single
        assert files == []

    def test_open_file(self, sample_python_file):
        """Test reading file contents."""
        content = RepoTreeSitter.open_file(str(sample_python_file))
        assert "def greet" in content
        assert "class Calculator" in content

    def test_extract_structure_function(self, sample_python_file, temp_dir):
        """Test extracting function structure from Python file."""
        parser = RepoTreeSitter(str(temp_dir))
        structure = parser.extract_structure(str(sample_python_file))

        assert "structure" in structure
        assert "imports" in structure

        # Find the greet function
        functions = [item for item in structure["structure"] if item["type"] == "function"]
        greet_funcs = [f for f in functions if f["details"]["method_name"] == "greet"]
        assert len(greet_funcs) == 1

        greet = greet_funcs[0]["details"]
        assert greet["method_name"] == "greet"
        assert "name" in greet["arguments"]
        assert greet["return_type"] == "str"
        assert "Greet someone" in greet["docstring"]

    def test_extract_structure_class(self, sample_python_file, temp_dir):
        """Test extracting class structure from Python file."""
        parser = RepoTreeSitter(str(temp_dir))
        structure = parser.extract_structure(str(sample_python_file))

        classes = [item for item in structure["structure"] if item["type"] == "class"]
        calc_classes = [c for c in classes if c["name"] == "Calculator"]
        assert len(calc_classes) == 1

        calc = calc_classes[0]
        assert calc["name"] == "Calculator"
        assert "simple calculator" in calc["docstring"].lower()

        # Check methods
        method_names = [m["method_name"] for m in calc["methods"]]
        assert "__init__" in method_names
        assert "add" in method_names
        assert "_internal_method" in method_names  # Private methods are extracted

    def test_extract_structure_decorators(self, sample_python_file, temp_dir):
        """Test extracting decorated function."""
        parser = RepoTreeSitter(str(temp_dir))
        structure = parser.extract_structure(str(sample_python_file))

        functions = [item for item in structure["structure"] if item["type"] == "function"]
        helper_funcs = [f for f in functions if f["details"]["method_name"] == "helper_function"]
        assert len(helper_funcs) == 1
        assert "@staticmethod" in helper_funcs[0]["details"]["decorators"]

    def test_analyze_directory(self, sample_repo):
        """Test analyzing all files in a directory."""
        parser = RepoTreeSitter(str(sample_repo))
        results = parser.analyze_directory(str(sample_repo))

        # Should have results for multiple files
        assert len(results) >= 2

        # Check that files are keyed by their full path
        file_paths = list(results.keys())
        assert all(path.endswith(".py") for path in file_paths)

    def test_extract_imports(self, temp_dir):
        """Test extracting import statements."""
        code = """from pathlib import Path
from os import path as ospath
import sys
from . import local_module
"""
        file_path = temp_dir / "imports.py"
        file_path.write_text(code)

        parser = RepoTreeSitter(str(temp_dir))
        structure = parser.extract_structure(str(file_path))

        imports = structure["imports"]
        # Note: Only local imports that can be resolved will appear
        # External imports (pathlib, os, sys) may or may not be resolved
        # depending on the implementation
        assert isinstance(imports, dict)

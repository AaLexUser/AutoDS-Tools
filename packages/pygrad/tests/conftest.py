"""Pytest fixtures for pygrad tests."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_python_file(temp_dir):
    """Create a sample Python file for testing."""
    code = '''"""Sample module docstring."""


def greet(name: str) -> str:
    """Greet someone by name.

    Args:
        name: The name to greet

    Returns:
        A greeting string
    """
    return f"Hello, {name}!"


class Calculator:
    """A simple calculator class."""

    def __init__(self, initial_value: int = 0):
        """Initialize the calculator.

        Args:
            initial_value: Starting value
        """
        self.value = initial_value

    def add(self, x: int) -> int:
        """Add x to the current value."""
        self.value += x
        return self.value

    def _internal_method(self):
        """This should be excluded (private)."""
        pass


@staticmethod
def helper_function():
    """A decorated function."""
    pass
'''
    file_path = temp_dir / "sample.py"
    file_path.write_text(code)
    return file_path


@pytest.fixture
def sample_repo(temp_dir):
    """Create a sample repository structure for testing."""
    # Create package structure
    pkg_dir = temp_dir / "mypackage"
    pkg_dir.mkdir()

    # __init__.py
    (pkg_dir / "__init__.py").write_text('"""My package."""\n')

    # core.py
    core_code = '''"""Core module."""


class Core:
    """Core class."""

    def __init__(self):
        """Initialize Core."""
        pass

    def run(self) -> None:
        """Run the core."""
        pass
'''
    (pkg_dir / "core.py").write_text(core_code)

    # utils.py
    utils_code = '''"""Utilities module."""


def helper() -> str:
    """A helper function."""
    return "help"
'''
    (pkg_dir / "utils.py").write_text(utils_code)

    # tests directory (should be excluded)
    tests_dir = temp_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("")
    (tests_dir / "test_core.py").write_text("def test_example(): pass\n")

    return temp_dir


@pytest.fixture
def sample_api_xml(temp_dir):
    """Create a sample api.xml file for testing."""
    xml_content = """<?xml version="1.0" ?>
<repository>
  <important_files>
    <file score="100">mypackage/core.py</file>
    <file score="50">mypackage/utils.py</file>
  </important_files>
  <class>
    <name>Calculator</name>
    <api_path>mypackage.Calculator</api_path>
    <description>A simple calculator class.</description>
    <initialization>
      <parameters>initial_value: int = 0</parameters>
      <description>Initialize the calculator.</description>
    </initialization>
    <methods>
      <method>
        <name>add</name>
        <api_path>mypackage.Calculator.add</api_path>
        <description>Add x to the current value.</description>
        <header>def add(self, x: int) -> int</header>
        <output></output>
        <usage_examples>
          <example>
            <from>examples/demo.py</from>
            <type>usage</type>
            <source_code>calc = Calculator()
result = calc.add(5)</source_code>
          </example>
        </usage_examples>
      </method>
    </methods>
    <usage_examples></usage_examples>
  </class>
  <function>
    <name>greet</name>
    <api_path>mypackage.greet</api_path>
    <description>Greet someone by name.</description>
    <header>def greet(name: str) -> str</header>
    <output></output>
    <usage_examples></usage_examples>
  </function>
</repository>"""
    file_path = temp_dir / "api.xml"
    file_path.write_text(xml_content)
    return file_path

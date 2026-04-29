"""Tests for PythonRepositoryProcessor."""

from pygrad.processor.processor import (
    ClassInfo,
    FunctionInfo,
    PythonRepositoryProcessor,
)


class TestPythonRepositoryProcessor:
    """Tests for PythonRepositoryProcessor class."""

    def test_init(self, sample_repo):
        """Test processor initialization."""
        processor = PythonRepositoryProcessor(str(sample_repo))
        assert processor.repo_path == sample_repo
        assert processor.analysis_results == {}

    def test_process_repository_data(self, sample_repo):
        """Test processing repository to get classes and functions."""
        processor = PythonRepositoryProcessor(str(sample_repo))
        classes, functions = processor.process_repository_data()

        # Should find Core class from mypackage/core.py
        class_names = [c.name for c in classes]
        assert "Core" in class_names

        # Should find helper function from mypackage/utils.py
        func_names = [f.name for f in functions]
        assert "helper" in func_names

    def test_process_repository_excludes_tests(self, sample_repo):
        """Test that test directories are excluded."""
        processor = PythonRepositoryProcessor(str(sample_repo))
        _classes, functions = processor.process_repository_data()

        # test_core.py has test_example function, should be excluded
        func_names = [f.name for f in functions]
        assert "test_example" not in func_names

        # Check API paths don't include "tests"
        for func in functions:
            assert "tests" not in func.api_path.lower()

    def test_get_module_path(self, sample_repo):
        """Test module path generation."""
        processor = PythonRepositoryProcessor(str(sample_repo))

        # Test module path for a file in mypackage/
        module_path = processor._get_module_path(str(sample_repo / "mypackage" / "core.py"))
        assert module_path == "mypackage.core"

    def test_clean_docstring(self, sample_repo):
        """Test docstring cleaning."""
        processor = PythonRepositoryProcessor(str(sample_repo))

        # Test with triple quotes
        assert processor._clean_docstring('"""Hello"""') == "Hello"
        assert processor._clean_docstring("'''Hello'''") == "Hello"

        # Test with whitespace
        assert processor._clean_docstring("  Hello  ") == "Hello"

        # Test with None
        assert processor._clean_docstring(None) == ""

    def test_save_repository_data(self, sample_repo):
        """Test saving data to XML file."""
        processor = PythonRepositoryProcessor(str(sample_repo))

        # Create some test data
        classes = [
            ClassInfo(
                name="TestClass",
                api_path="test.TestClass",
                description="A test class",
                initialization={"parameters": "self, x", "description": "Init"},
                methods=[],
                usage_examples=[],
            )
        ]
        functions = [
            FunctionInfo(
                name="test_func",
                api_path="test.test_func",
                description="A test function",
                header="def test_func(x: int) -> str",
                output="",
                usage_examples=[],
            )
        ]
        important_files = [("test.py", 100.0)]

        output_path = processor.save_repository_data(classes, functions, important_files, "test_api.xml")

        assert output_path.endswith("test_api.xml")

        # Read and verify XML content
        with open(output_path) as f:
            content = f.read()

        assert "TestClass" in content
        assert "test_func" in content
        assert "test.py" in content

    def test_generate_xml_structure(self, sample_repo):
        """Test XML generation structure."""
        processor = PythonRepositoryProcessor(str(sample_repo))

        classes = [
            ClassInfo(
                name="MyClass",
                api_path="pkg.MyClass",
                description="Description",
                initialization={"parameters": "self", "description": "Init"},
                methods=[
                    FunctionInfo(
                        name="method",
                        api_path="pkg.MyClass.method",
                        description="A method",
                        header="def method(self)",
                        output="None",
                        usage_examples=[],
                    )
                ],
                usage_examples=[],
            )
        ]
        functions = []
        important_files = [("file.py", 50.0)]

        xml_content = processor._generate_xml(classes, functions, important_files)

        # Verify XML structure
        assert "<repository>" in xml_content
        assert "<class>" in xml_content
        assert "<name>MyClass</name>" in xml_content
        assert "<method>" in xml_content
        assert "<important_files>" in xml_content


class TestDataClasses:
    """Tests for data classes."""

    def test_function_info_creation(self):
        """Test FunctionInfo dataclass."""
        func = FunctionInfo(
            name="my_func",
            api_path="module.my_func",
            description="Does something",
            header="def my_func(x: int) -> str",
            output="str",
            usage_examples=["example1", "example2"],
        )

        assert func.name == "my_func"
        assert func.api_path == "module.my_func"
        assert len(func.usage_examples) == 2

    def test_class_info_creation(self):
        """Test ClassInfo dataclass."""
        cls = ClassInfo(
            name="MyClass",
            api_path="module.MyClass",
            description="A class",
            initialization={"parameters": "self, x", "description": "Init"},
            methods=[],
            usage_examples=[],
        )

        assert cls.name == "MyClass"
        assert cls.initialization["parameters"] == "self, x"

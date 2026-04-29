"""Tests for XML API entity extraction."""

import pytest

from pygrad.xmlapi import extract_entities


class TestExtractEntities:
    """Tests for extract_entities function."""

    def test_extract_classes(self, sample_api_xml):
        """Test extracting class information from XML."""
        classes, _methods, _functions, _examples = extract_entities(sample_api_xml)

        assert len(classes) == 1
        class_text = classes[0]
        assert "Class: Calculator" in class_text
        assert "mypackage.Calculator" in class_text
        assert "simple calculator" in class_text.lower()

    def test_extract_methods(self, sample_api_xml):
        """Test extracting method information from XML."""
        _classes, methods, _functions, _examples = extract_entities(sample_api_xml)

        assert len(methods) == 1
        method_text = methods[0]
        assert "Method: Calculator.add" in method_text
        assert "def add(self, x: int) -> int" in method_text

    def test_extract_functions(self, sample_api_xml):
        """Test extracting function information from XML."""
        _classes, _methods, functions, _examples = extract_entities(sample_api_xml)

        assert len(functions) == 1
        func_text = functions[0]
        assert "Function: greet" in func_text
        assert "mypackage.greet" in func_text
        assert "def greet(name: str) -> str" in func_text

    def test_extract_examples(self, sample_api_xml):
        """Test extracting usage examples from XML."""
        _classes, _methods, _functions, examples = extract_entities(sample_api_xml)

        assert len(examples) == 1
        example_text = examples[0]
        assert "example" in example_text.lower()
        assert "calc = Calculator()" in example_text
        assert "calc.add(5)" in example_text

    def test_empty_xml(self, temp_dir):
        """Test extracting from minimal XML."""
        xml_content = '<?xml version="1.0" ?><repository></repository>'
        file_path = temp_dir / "empty.xml"
        file_path.write_text(xml_content)

        classes, methods, functions, examples = extract_entities(file_path)

        assert classes == []
        assert methods == []
        assert functions == []
        assert examples == []

    def test_invalid_xml_raises_error(self, temp_dir):
        """Test that invalid XML raises RuntimeError."""
        file_path = temp_dir / "invalid.xml"
        file_path.write_text("not valid xml content")

        with pytest.raises(RuntimeError, match="Error extracting entities"):
            extract_entities(file_path)

    def test_nonexistent_file_raises_error(self, temp_dir):
        """Test that nonexistent file raises RuntimeError."""
        file_path = temp_dir / "nonexistent.xml"

        with pytest.raises(RuntimeError, match="Error extracting entities"):
            extract_entities(file_path)

    def test_class_with_initialization(self, sample_api_xml):
        """Test that initialization info is extracted."""
        classes, _methods, _functions, _examples = extract_entities(sample_api_xml)

        class_text = classes[0]
        assert "initial_value" in class_text
        assert "__init__" in class_text

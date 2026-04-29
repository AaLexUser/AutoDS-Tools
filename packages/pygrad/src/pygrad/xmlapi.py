"""XML API documentation entity extraction."""

import xml.etree.ElementTree as ET
from pathlib import Path


def _get_text(elem: ET.Element, tag: str, default: str = "") -> str:
    """Get text content of a child element."""
    child = elem.find(tag)
    return child.text if child is not None and child.text else default


def _get_examples(elem: ET.Element) -> list[str]:
    """Extract usage examples from an element."""
    examples_elem = elem.find("usage_examples")
    if examples_elem is None:
        return []

    examples = []
    for example_elem in examples_elem.findall("example"):
        from_ = _get_text(example_elem, "from")
        type_ = _get_text(example_elem, "type")
        source_code = _get_text(example_elem, "source_code")

        if source_code.strip():
            examples.append(f'<example from="{from_}" type="{type_}">\n{source_code}\n</example>')
    return examples


def extract_entities(
    xml_api_path: Path,
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Extract top-level entities from API XML documentation.

    Args:
        xml_api_path: Path to the api.xml file

    Returns:
        Tuple of (classes, methods, functions, examples) as formatted strings

    Raises:
        RuntimeError: If parsing fails
    """
    try:
        tree = ET.parse(xml_api_path)
        root = tree.getroot()

        classes: list[str] = []
        methods: list[str] = []
        functions: list[str] = []
        examples: list[str] = []

        # Extract classes and their methods
        for class_elem in root.findall("class"):
            name = _get_text(class_elem, "name", "Unknown")
            api_path = _get_text(class_elem, "api_path", "")
            description = _get_text(class_elem, "description", "")

            overview_parts = [f"Class: {name}"]
            if api_path:
                overview_parts.append(f"API Path: {api_path}")
            if description:
                overview_parts.append(f"Description: {description}")

            # Add initialization info
            init_elem = class_elem.find("initialization")
            if init_elem is not None:
                params = _get_text(init_elem, "parameters", "")
                init_desc = _get_text(init_elem, "description", "")
                if params:
                    overview_parts.append(f"Initialization: __init__({params})")
                if init_desc:
                    overview_parts.append(f"Init Description: {init_desc}")

            classes.append("\n".join(overview_parts))
            examples.extend(_get_examples(class_elem))

            # Extract methods
            methods_elem = class_elem.find("methods")
            if methods_elem is not None:
                for method_elem in methods_elem.findall("method"):
                    method_name = _get_text(method_elem, "name", "unknown")
                    method_desc = _get_text(method_elem, "description", "")
                    method_header = _get_text(method_elem, "header", "")
                    method_output = _get_text(method_elem, "output", "")

                    method_parts = [f"Method: {name}.{method_name}"]
                    if method_header:
                        method_parts.append(f"Signature: {method_header}")
                    if method_desc:
                        method_parts.append(f"Description: {method_desc}")
                    if method_output:
                        method_parts.append(f"Output: {method_output}")

                    methods.append("\n".join(method_parts))
                    examples.extend(_get_examples(method_elem))

        # Extract standalone functions
        for function_elem in root.findall("function"):
            name = _get_text(function_elem, "name", "Unknown")
            api_path = _get_text(function_elem, "api_path", "")
            description = _get_text(function_elem, "description", "")
            header = _get_text(function_elem, "header", "")
            output = _get_text(function_elem, "output", "")

            text_parts = [f"Function: {name}"]
            if api_path:
                text_parts.append(f"API Path: {api_path}")
            if header:
                text_parts.append(f"Signature: {header}")
            if description:
                text_parts.append(f"Description: {description}")
            if output:
                text_parts.append(f"Output: {output}")

            functions.append("\n".join(text_parts))
            examples.extend(_get_examples(function_elem))

        return classes, methods, functions, examples

    except Exception as e:
        raise RuntimeError(f"Error extracting entities from api.xml: {e}") from e

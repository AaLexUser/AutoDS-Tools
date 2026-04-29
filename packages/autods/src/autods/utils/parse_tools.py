import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Tuple

from autods.tools.base import BaseToolCall

INVALID_TOOLS = {"thinking", "reasoning"}


def _parse_xml_tool_calls(text: str, positions: List[Tuple[int, BaseToolCall]]) -> None:
    """Extract XML-style tool calls from text and add to positions list."""
    tool_pattern = re.compile(
        r"<(?P<tag>[A-Za-z_][A-Za-z0-9_\-]*)\b[^>]*>(?P<body>.*?)</(?P=tag)>",
        re.DOTALL,
    )

    for match in tool_pattern.finditer(text):
        tag = match.group("tag")
        body = match.group("body")

        # Extract the full opening tag including attributes
        full_match = match.group(0)
        opening_tag_match = re.match(rf"<{tag}\b([^>]*)>", full_match)
        opening_tag = opening_tag_match.group(0) if opening_tag_match else f"<{tag}>"

        # Skip invalid tools
        if tag in INVALID_TOOLS:
            continue

        # Parse the tool call as XML to extract structured parameters
        try:
            xml_content = f"{opening_tag}{body}</{tag}>"
            elem = ET.fromstring(xml_content)

            params = _extract_xml_parameters(elem)

            if params:  # Only add if we have valid parameters
                tool_call = BaseToolCall(name=tag, params=params)
                positions.append((match.start(), tool_call))

        except ET.ParseError:
            # Fallback: try to recover attributes via regex and use body as 'arg'
            if body.strip():
                params = {"arg": body.strip()}

                # Try to extract attributes from the opening tag using regex
                # Matches key="value" or key='value'
                attr_pattern = re.compile(r'(\w+)=["\']([^"\']+)["\']')
                for attr_match in attr_pattern.finditer(opening_tag):
                    key, value = attr_match.groups()
                    params[key] = value

                tool_call = BaseToolCall(name=tag, params=params)
                positions.append((match.start(), tool_call))


def _parse_self_closing_xml_tags(text: str, positions: List[Tuple[int, BaseToolCall]]) -> None:
    """Extract self-closing XML-style tool calls like <tag attr="value" />."""
    pattern = re.compile(
        r"<(?P<tag>[A-Za-z_][A-Za-z0-9_\-]*)\b(?P<attrs>[^>]*?)\s*/>",
        re.DOTALL,
    )

    for match in pattern.finditer(text):
        tag = match.group("tag")
        attrs_str = match.group("attrs")

        if tag in INVALID_TOOLS:
            continue

        # Extract attributes using regex
        params: Dict[str, Any] = {}
        attr_pattern = re.compile(r'(\w+)=["\']([^"\']*)["\']')
        for attr_match in attr_pattern.finditer(attrs_str):
            key, value = attr_match.groups()
            params[key] = value

        if params:  # Only add if we have valid parameters
            tool_call = BaseToolCall(name=tag, params=params)
            positions.append((match.start(), tool_call))


def _extract_xml_parameters(elem: ET.Element) -> Dict[str, Any]:
    """Extract parameters from XML element."""
    params: Dict[str, Any] = {}

    for key, value in elem.attrib.items():
        params[key] = value

    for child in list(elem):
        if isinstance(child.tag, str):
            key = child.tag.strip()
            value = "".join(child.itertext()).strip()
            if value:  # Only add non-empty values
                params[key] = value

    # Use text content as 'arg'
    if elem.text:
        text_value = elem.text.strip()
        if text_value:
            params["arg"] = text_value

    return params


def parse_tools_from_message(message: str) -> List[BaseToolCall]:
    """Parse all possible tool calls from an AIMessage.

    Approach:
    - First extract markdown code blocks for known tools
    - Then extract XML-style tool calls like <name> ... </name>
    - Parse each candidate with ElementTree to build BaseToolCall objects
    - Maintain original order of tools as they appear in the message
    """
    raw_text = message.strip()
    if not raw_text:
        return []

    tool_positions: List[Tuple[int, BaseToolCall]] = []

    # _parse_markdown_codeblocks(raw_text, tool_positions)

    _parse_xml_tool_calls(raw_text, tool_positions)
    _parse_self_closing_xml_tags(raw_text, tool_positions)

    tool_positions.sort(key=lambda x: x[0])
    return [call for _, call in tool_positions]

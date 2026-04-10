"""Display utilities for Jupyter executor.

This module contains functions for displaying code and markdown content
using Rich console formatting.
"""

import re
from typing import Literal

from rich.box import MINIMAL
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax


def render_markdown(content: str) -> None:
    """Display markdown content with proper formatting."""
    matches = re.finditer(r"```(.+?)```", content, re.DOTALL)
    start_index = 0
    content_panels = []
    style = "black on white"

    for match in matches:
        text_content = content[start_index : match.start()].strip()
        code_content = match.group(0).strip()[3:-3]

        if text_content:
            content_panels.append(
                Panel(Markdown(text_content), style=style, box=MINIMAL)
            )

        if code_content:
            content_panels.append(
                Panel(Markdown(f"```{code_content}"), style=style, box=MINIMAL)
            )
        start_index = match.end()

    remaining_text = content[start_index:].strip()
    if remaining_text:
        content_panels.append(Panel(Markdown(remaining_text), style=style, box=MINIMAL))

    with Live(
        auto_refresh=False, console=Console(), vertical_overflow="visible"
    ) as live:
        live.update(Group(*content_panels))
        live.refresh()


def display_code(
    code: str,
    console: Console,
    language: Literal["python", "markdown", "shell"] = "python",
) -> None:
    """Display code, shell, or markdown content in the console."""
    display_map = {
        "python": lambda: console.print(
            Syntax(code, "python", theme="paraiso-dark", line_numbers=True)
        ),
        "shell": lambda: console.print(
            Syntax(code, "bash", theme="paraiso-dark", line_numbers=True)
        ),
        "markdown": lambda: render_markdown(code),
    }

    if language not in display_map:
        raise ValueError(
            f"Only support for python, markdown, shell, but got {language}"
        )

    display_map[language]()

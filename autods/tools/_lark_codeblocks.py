from __future__ import annotations

"""
Lark grammar for fenced code blocks.

Supported:
- Triple backtick blocks only.
- Languages: python|py -> "python"; bash|sh|shell|zsh -> "bash".
- Ignores all other languages and non-fenced text outside blocks.

Notes:
- We intentionally restrict to ```...``` for the current use‑case.
- The CLOSE fence may be at end of file without a trailing newline.
"""

from typing import Literal

from lark import Lark, Transformer, v_args

NormalizedLang = Literal["python", "bash"]


GRAMMAR = r"""
start: (nonblock | block)*

nonblock: NBLINE

block: OPEN body CLOSE

OPEN: /```[ \t]*[^\r\n]*\r?\n/
CLOSE: /```[ \t]*\r?\n/ | /```[ \t]*$/
LINE: /(?!```)[^\r\n]*\r?\n/

// NBLINE is any non-fence line outside of a block
NBLINE: /(?!```)[^\r\n]*\r?\n/

body: LINE*
"""


def _normalize_lang_from_open(open_token: str) -> str:
    """Extract and normalize language tag from the OPEN header token."""
    header = open_token.strip()  # like "```python" or "```bash -x"
    # remove initial ``` and any spaces following
    rest = header[3:].lstrip()
    # pull the first word as a tag
    tag = ""
    for ch in rest:
        if ch.isspace():
            break
        tag += ch
    low = tag.lower()
    if low in {"python", "py"}:
        return "python"
    if low in {"bash", "sh", "shell", "zsh"}:
        return "bash"
    return ""  # unknown/unsupported


@v_args(inline=True)
class _Tx(Transformer):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[tuple[str, str]] = []

    def OPEN(self, tok):  # type: ignore[override]
        return str(tok)

    def CLOSE(self, _tok):  # type: ignore[override]
        return None

    def LINE(self, tok):  # type: ignore[override]
        return str(tok)

    def body(self, *lines):  # type: ignore[override]
        return "".join(str(l) for l in lines)

    def block(self, open_tok, body, _close):  # type: ignore[override]
        lang = _normalize_lang_from_open(str(open_tok))
        if lang:
            # Preserve exact body text (no trimming) minus a final trailing newline
            code = str(body)
            self.blocks.append((lang, code))

    def start(self, *_):  # type: ignore[override]
        return self.blocks


def parse_fenced_blocks(payload: str) -> list[tuple[NormalizedLang, str]]:
    """Parse ``payload`` and return a list of (lang, code) tuples.

    This accepts triple backtick fences even if they appear mid-line in the
    surrounding prose. A light normalization step moves any "```" fences to
    their own lines to simplify grammar while preserving content.
    """
    text = payload or ""

    # Normalize: ensure any ``` fences are on their own lines so lexer tokens
    # don't consume them as part of non-fence lines.
    # - Insert a newline before any fence not at line start
    # - Insert a newline after any fence not followed by a newline
    # This is conservative and should not alter code meaning.
    import re

    def _preprocess(s: str) -> str:
        # newline before fences not at line start
        s = re.sub(r"([^\n])```", r"\1\n```", s)
        # newline after closing fences that are followed by non-newline and not a language tag
        # Avoid splitting language headers like "```python".
        s = re.sub(r"```(?![A-Za-z0-9_])([^\n])", r"```\n\1", s)
        return s

    normalized = _preprocess(text)
    if not normalized.endswith("\n"):
        normalized += "\n"

    parser = Lark(GRAMMAR, start="start", parser="lalr")
    tree = parser.parse(normalized)
    blocks = _Tx().transform(tree)
    # type narrowing + normalization
    out: list[tuple[NormalizedLang, str]] = []
    for lang, code in blocks:
        if lang == "python":
            out.append(("python", code))
        elif lang == "bash":
            out.append(("bash", code))
    return out

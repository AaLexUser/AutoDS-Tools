"""Classify API elements by structural role for embedding text.

Uses path and naming conventions that generalize across Python libraries,
not library-specific symbol names.
"""

from __future__ import annotations

ENTRY_POINT_MARKERS = (".presets.", ".cli.", ".client.", ".api.", ".main.")
INTERNAL_PATH_MARKERS = (".base.", ".internal.", ".abstract.", "._")
UTILITY_PATH_PARTS = (".utils.", ".logging.", ".validation.", ".report.", ".helpers.", ".common.")
INTERNAL_NAME_SUFFIXES = ("Base", "Wrapper", "Protocol", "Mixin", "abc")


def classify_api_tier(api_path: str, name: str, node_type: str) -> str:
    """Return a tier label stored on graph nodes and used in embedding text."""
    if node_type == "Example":
        return "example"

    if node_type in {"Class", "Function"} and any(marker in api_path for marker in ENTRY_POINT_MARKERS):
        return "entry_point"

    if any(marker in api_path for marker in INTERNAL_PATH_MARKERS):
        return "internal"

    if any(name.endswith(suffix) for suffix in INTERNAL_NAME_SUFFIXES):
        return "internal"

    if any(part in api_path for part in UTILITY_PATH_PARTS):
        return "utility"

    if node_type == "Method" and name.startswith("_"):
        return "internal"

    if node_type == "Method":
        return "method"

    if node_type == "Function":
        return "function"

    return "api"


def tier_label_for_embedding(tier: str) -> str:
    """Human-readable tier prefix for embedding text."""
    labels = {
        "entry_point": "recommended public entry point",
        "api": "public API",
        "function": "public function",
        "method": "method",
        "internal": "internal implementation",
        "utility": "utility",
        "example": "usage example",
    }
    return labels.get(tier, tier)


_TOPIC_TERMS = (
    "classification",
    "binary",
    "multiclass",
    "regression",
    "tabular",
    "text",
    "nlp",
    "natural language",
    "image",
    "computer vision",
    "time series",
    "forecasting",
    "clustering",
    "embedding",
    "metric",
    "cross-validation",
)


def infer_topic_hints(description: str) -> str:
    """Extract topic hints from a docstring/description (no symbol-specific rules)."""
    if not description:
        return ""
    text = description.lower()
    found = [term for term in _TOPIC_TERMS if term in text]
    if not found:
        return ""
    return "Topics: " + ", ".join(dict.fromkeys(found))

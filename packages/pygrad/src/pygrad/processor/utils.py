"""Utilities for ranking and extracting important files from repositories."""

import os
from collections import Counter
from pathlib import Path
from typing import Any

from pygrad.parser.treesitter import RepoTreeSitter


def extract_test_example_paths(repo_path: Path) -> dict[str, list[str]]:
    """Extract paths to test and example directories in a repository.

    Searches up to 2 levels deep from the repository root.

    Args:
        repo_path: Path to the repository root directory

    Returns:
        Dictionary with 'test' and 'example' keys containing lists of paths
    """
    result: dict[str, list[str]] = {"test": [], "example": []}

    if not repo_path.exists() or not repo_path.is_dir():
        return result

    test_patterns = {"test", "tests", "testing", "spec", "specs"}
    example_patterns = {
        "example",
        "examples",
        "tutorial",
        "tutorials",
        "demo",
        "demos",
        "sample",
        "samples",
        "doc",
        "docs",
    }

    def matches_pattern(dirname: str, patterns: set[str]) -> bool:
        dirname_lower = dirname.lower()
        return dirname_lower in patterns or any(p in dirname_lower for p in patterns)

    for root, dirs, _ in os.walk(repo_path):
        relative_path = os.path.relpath(root, repo_path)
        depth = 0 if relative_path == "." else len(relative_path.split(os.sep))

        if depth > 2:
            dirs.clear()
            continue

        dirs_to_remove = []
        for dirname in dirs:
            dir_path = os.path.join(root, dirname)

            if matches_pattern(dirname, test_patterns):
                result["test"].append(dir_path)
                dirs_to_remove.append(dirname)
            elif matches_pattern(dirname, example_patterns):
                result["example"].append(dir_path)
                dirs_to_remove.append(dirname)

        for dirname in dirs_to_remove:
            if dirname in dirs:
                dirs.remove(dirname)

    result["test"] = sorted(set(result["test"]))
    result["example"] = sorted(set(result["example"]))
    return result


def extract_important_api(repo_path: Path, top_n: int = 15) -> list[tuple[str, float]]:
    """Extract important API files from a repository.

    Uses multi-factor scoring to rank files by importance.

    Args:
        repo_path: Path to the repository
        top_n: Number of top files to return (0 for all)

    Returns:
        List of tuples (file_path, score) sorted by score descending
    """
    test_example_paths = extract_test_example_paths(repo_path)
    test_paths = test_example_paths["test"]
    example_paths = test_example_paths["example"]

    treesitter = RepoTreeSitter(str(repo_path))
    structure = treesitter.analyze_directory(str(repo_path))

    exclusions = [".git", ".github", "__init__", "__pycache__", *test_paths, *example_paths]

    included = {}
    excluded = {}
    for key, value in structure.items():
        if any(ex in key for ex in exclusions):
            excluded[key] = value
        else:
            included[key] = value

    results = _rank_by_multi_factor_scoring(included, excluded, repo_path)
    return results[:top_n] if top_n > 0 else results


def _get_import_counts(parsed_structure: dict[str, Any]) -> Counter[str]:
    """Get import counts for each file in the parsed structure."""
    all_import_paths: list[str] = [
        import_info["path"]
        for structure in parsed_structure.values()
        for import_info in structure.get("imports", {}).values()
        if isinstance(import_info, dict) and "path" in import_info
    ]
    return Counter(all_import_paths)


def _rank_by_multi_factor_scoring(
    included: dict[str, Any], excluded: dict[str, Any], repo_path: Path
) -> list[tuple[str, float]]:
    """Rank files using multi-factor scoring."""
    internal_imports = _get_import_counts(included)
    test_imports = _get_import_counts(excluded) if excluded else Counter()

    file_scores = [
        (
            file_path,
            _score_file_importance(
                file_path,
                repo_path,
                file_structure,
                test_imports,
                internal_imports,
            ),
        )
        for file_path, file_structure in included.items()
    ]

    file_scores.sort(key=lambda x: x[1], reverse=True)

    # Filter out low-value files
    filtered = []
    for file_path, score in file_scores:
        filename = Path(file_path).stem

        if filename in ("utils", "helpers", "helper", "util") and score < 10:
            continue
        if filename.startswith("_") and filename not in ("__init__", "__main__") and score < 50:
            continue
        if filename == "__init__":
            continue

        filtered.append((file_path, score))

    return filtered


def _score_file_importance(
    file_path: str,
    repo_path: Path,
    file_structure: dict[str, Any],
    test_imports: Counter[str],
    internal_imports: Counter[str],
) -> float:
    """Calculate composite importance score for a file."""
    score = 0.0

    # External usage (30%)
    test_count = test_imports.get(file_path, 0)
    external_score = min(test_count * 15, 100)
    score += (external_score / 100) * 30

    # Internal import ratio (20%)
    internal_count = internal_imports.get(file_path, 0)
    if test_count > 0:
        ratio = test_count / (internal_count + 1)
        score += (min(ratio * 20, 100) / 100) * 20

    # Package hierarchy (15%)
    score += (_hierarchy_score(file_path, repo_path) / 100) * 15

    # Naming conventions (10%)
    score += (_naming_score(file_path) / 100) * 10

    # Documentation richness (10%)
    score += (_documentation_score(file_structure) / 100) * 10

    # Code metrics (10%)
    score += (_code_metrics_score(file_structure) / 100) * 10

    # Import fanout (5%)
    fanout = internal_imports.get(file_path, 0)
    score += (min(fanout * 2, 100) / 100) * 5

    return score


def _hierarchy_score(file_path: str, repo_path: Path) -> float:
    """Score based on package hierarchy depth."""
    path = Path(file_path)
    try:
        relative = path.relative_to(repo_path)
    except ValueError:
        relative = path

    score = 40.0 if path.stem in ("cli", "main", "__main__") else 0.0

    depth = len(relative.parts) - 1
    if depth == 0:
        score += 30
    elif depth == 1:
        score += 10
    elif depth == 2:
        score += 5

    return min(score, 100)


def _naming_score(file_path: str) -> float:
    """Score based on file naming conventions."""
    filename = Path(file_path).stem
    score = 0.0

    if any(name in filename.lower() for name in ("base", "core", "api", "client", "interface")):
        score += 20
    if filename.startswith("_") and filename not in ("__init__", "__main__"):
        score -= 20
    if filename in ("utils", "helpers"):
        score += 5

    return max(min(score, 100), 0)


def _documentation_score(file_structure: dict[str, Any]) -> float:
    """Score based on documentation richness."""
    if not file_structure:
        return 0.0

    structure = file_structure.get("structure", [])
    docstring_count = 0
    total_items = 0

    for item in structure:
        total_items += 1
        if item.get("docstring"):
            docstring_count += 1
        if item["type"] == "class":
            for method in item.get("methods", []):
                total_items += 1
                if method.get("docstring"):
                    docstring_count += 1

    if total_items > 0:
        return (docstring_count / total_items) * 15
    return 0.0


def _code_metrics_score(file_structure: dict[str, Any]) -> float:
    """Score based on code metrics like OOP patterns."""
    if not file_structure:
        return 0.0

    structure = file_structure.get("structure", [])
    class_count = sum(1 for item in structure if item["type"] == "class")
    function_count = sum(1 for item in structure if item["type"] == "function")

    score = 0.0
    total = function_count + class_count
    if (total > 0 and class_count / total > 0.5) or class_count > 0:
        score += 10

    for item in structure:
        if item["type"] == "class":
            class_name = item.get("name", "")
            if any(kw in class_name for kw in ("Base", "Abstract", "Protocol", "Interface")):
                score += 15
                break

    return min(score, 100)

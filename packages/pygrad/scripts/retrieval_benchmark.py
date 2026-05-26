"""Retrieval quality benchmark for pygrad GraphRAG.

Run against a live Neo4j index:
    uv run python packages/pygrad/scripts/retrieval_benchmark.py

Requires NEO4J_* and EMBEDDING_* env vars (load from repo .env).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from neo4j import GraphDatabase

# Allow running as script from repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pygrad.graphrag.embeddings import create_embedder_from_env
from pygrad.graphrag.retriever import MultiIndexRetriever


@dataclass
class BenchmarkCase:
    query: str
    repository_id: str
    expected_paths: list[str] = field(default_factory=list)
    expected_patterns: list[str] = field(default_factory=list)
    noise_patterns: list[str] = field(default_factory=list)


BENCHMARK_CASES = [
    BenchmarkCase(
        query="how to solve classification task with LightAutoML",
        repository_id="sb-ai-lab-lightautoml",
        expected_paths=[
            "lightautoml.automl.presets.tabular_presets.TabularAutoML",
            "lightautoml.tasks.Task",
        ],
        expected_patterns=["TabularAutoML", "Task(", "fit_predict"],
        noise_patterns=[
            r"lightautoml\.automl\.base\.AutoML",
            r"AutoMLPreset\.",
            r"Wrapper\.",
            r"\.infer_auto_params",
            r"\.create_model_str_desc",
            r"LoggerStream",
        ],
    ),
    BenchmarkCase(
        query="how to do text classification with LightAutoML",
        repository_id="sb-ai-lab-lightautoml",
        expected_paths=[
            "lightautoml.automl.presets.text_presets.TabularNLPAutoML",
        ],
        expected_patterns=["TabularNLPAutoML", "Task("],
        noise_patterns=[
            r"lightautoml\.automl\.base\.AutoML",
            r"LoggerStream",
            r"\.infer_auto_params",
        ],
    ),
    BenchmarkCase(
        query="what is TabularAutoML",
        repository_id="sb-ai-lab-lightautoml",
        expected_paths=[
            "lightautoml.automl.presets.tabular_presets.TabularAutoML",
        ],
        expected_patterns=["TabularAutoML", "preset"],
        noise_patterns=[
            r"\.infer_auto_params",
            r"MLAlgoForAutoMLWrapper",
        ],
    ),
]


def _extract_result_id(content: str) -> str:
    match = re.search(r"^## (.+?) \(relevance:", content, re.M)
    if match:
        return match.group(1)
    match = re.search(r"^## Example from (.+?):", content, re.M)
    if match:
        return match.group(1)
    return content[:80]


def score_retrieval(results: list[str], case: BenchmarkCase) -> dict:
    """Score retrieval results for a benchmark case."""
    top5 = results[:5]
    combined = "\n".join(top5)

    expected_hits = 0
    first_rank: int | None = None
    for path in case.expected_paths:
        for i, item in enumerate(top5, 1):
            if path in item:
                expected_hits += 1
                if first_rank is None:
                    first_rank = i
                break

    pattern_hits = sum(1 for p in case.expected_patterns if p in combined)
    noise_hits = sum(
        1
        for item in top5
        for pattern in case.noise_patterns
        if re.search(pattern, _extract_result_id(item) + "\n" + item)
    )

    preset_in_top5 = int(
        any("TabularAutoML" in item and ".infer_auto_params" not in item for item in top5)
        or any("TabularNLPAutoML" in item for item in top5)
    )
    example_in_top5 = int(any(item.startswith("## Example from") for item in top5))

    relevance_score = (
        (1.0 if any(p in combined for p in case.expected_paths) else 0.0)
        + 0.3 * pattern_hits
        + 0.5 * example_in_top5
        - 0.2 * noise_hits
    )
    mrr = 1.0 / first_rank if first_rank else 0.0
    noise_ratio = noise_hits / max(len(top5), 1)

    return {
        "query": case.query,
        "relevance_score": round(relevance_score, 3),
        "mrr": round(mrr, 3),
        "noise_ratio": round(noise_ratio, 3),
        "preset_in_top5": preset_in_top5,
        "example_in_top5": example_in_top5,
        "expected_hits": expected_hits,
        "noise_hits": noise_hits,
        "top5": [_extract_result_id(r) for r in top5],
    }


async def run_benchmark(cases: list[BenchmarkCase] | None = None) -> dict:
    cases = cases or BENCHMARK_CASES
    uri = os.environ["NEO4J_URI"]
    auth = (os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"])
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    driver = GraphDatabase.driver(uri, auth=auth)
    embedder = create_embedder_from_env()

    report: dict = {"cases": [], "aggregate": {}}
    try:
        for case in cases:
            retriever = MultiIndexRetriever(driver, case.repository_id, embedder, database)
            results = await retriever.search(case.query, top_k=5)
            report["cases"].append(score_retrieval(results, case))
    finally:
        driver.close()

    scores = [c["relevance_score"] for c in report["cases"]]
    report["aggregate"] = {
        "mean_relevance_score": round(sum(scores) / len(scores), 3) if scores else 0.0,
        "mean_mrr": round(sum(c["mrr"] for c in report["cases"]) / len(report["cases"]), 3),
        "mean_noise_ratio": round(sum(c["noise_ratio"] for c in report["cases"]) / len(report["cases"]), 3),
    }
    return report


def main() -> None:
    report = asyncio.run(run_benchmark())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

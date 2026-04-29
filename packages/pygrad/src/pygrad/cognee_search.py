"""Cognee graph search: normalize API output to a single string (backend boundary)."""

from __future__ import annotations

from typing import Any
from uuid import UUID


def normalize_cognee_search_result(raw: Any) -> str:
    """Turn cognee.search return value into user-facing text."""
    if isinstance(raw, list):
        if not raw:
            return "No results found."
        parts: list[str] = []
        for item in raw:
            if isinstance(item, dict):
                sr = item.get("search_result", ["No results found."])
                if isinstance(sr, list) and sr:
                    parts.append(str(sr[0]))
                else:
                    parts.append("No results found.")
            else:
                parts.append(str(item))
        return "\n".join(parts)
    if raw and hasattr(raw, "result") and raw.result:
        return str(raw.result)
    return "No results found."


def _as_uuid(dataset_id: UUID | str) -> UUID:
    """Cognee expects dataset_ids as UUID, not str."""
    return dataset_id if isinstance(dataset_id, UUID) else UUID(dataset_id)


async def execute_cognee_search(
    dataset_id: UUID | str,
    query: str,
    system_prompt: str,
) -> str:
    """Run cognee search for a dataset and return normalized text."""
    import cognee
    from cognee.modules.engine.operations.setup import setup

    await setup()
    raw = await cognee.search(
        query_text=query,
        dataset_ids=[_as_uuid(dataset_id)],
        query_type=cognee.SearchType.GRAPH_COMPLETION_CONTEXT_EXTENSION,
        system_prompt=system_prompt,
    )
    return normalize_cognee_search_result(raw)

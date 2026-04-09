from __future__ import annotations

import asyncio
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
from langchain_core.messages import BaseMessage, BaseMessageChunk
from pydantic import BaseModel

from autods.constants import AUTODS_PACKAGE

DEFAULT_TRACING_PATH = AUTODS_PACKAGE / "tracing.yaml"


class Tracer:
    """Persist LangGraph debug stream chunks for offline inspection."""

    def __init__(self, file_path: str | Path | None = None, *, reset: bool = True):
        self.file_path = (
            Path(file_path) if file_path is not None else DEFAULT_TRACING_PATH
        )
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if reset:
            self.file_path.write_text("", encoding="utf-8")
        self._lock = asyncio.Lock()

    async def tracing_callback(self, mode: str, chunk: Any) -> None:
        if mode != "updates":
            return
        data = self._coerce(chunk)
        event_payload = {
            "mode": mode,
            "data": data,
        }
        async with self._lock:
            await asyncio.to_thread(self._persist_event, event_payload)

    def _persist_event(self, payload: dict[str, Any]) -> None:
        with self.file_path.open("a", encoding="utf-8") as handle:
            yaml.safe_dump(payload, handle, sort_keys=False)
            handle.write("---\n")

    def _coerce(
        self, value: Any, *, _seen: set[int] | None = None, _depth: int = 0
    ) -> Any:
        if _depth >= 20:
            return repr(value)
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, Enum):
            enum_value = value.value
            if isinstance(enum_value, (str, int, float, bool)) or enum_value is None:
                return enum_value
            return str(value)
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if _seen is None:
            _seen = set()
        obj_id = id(value)
        if obj_id in _seen:
            return repr(value)
        needs_tracking = (
            isinstance(value, (dict, list, tuple, set, frozenset))
            or hasattr(value, "__dict__")
            or (is_dataclass(value) and not isinstance(value, type))
        )
        if needs_tracking:
            _seen.add(obj_id)
        try:
            if isinstance(value, dict):
                return {
                    str(k): self._coerce(v, _seen=_seen, _depth=_depth + 1)
                    for k, v in value.items()
                }
            if isinstance(value, (list, tuple, set, frozenset)):
                return [
                    self._coerce(item, _seen=_seen, _depth=_depth + 1) for item in value
                ]
            if isinstance(value, BaseModel):
                return self._coerce(
                    value.model_dump(mode="json"),
                    _seen=_seen,
                    _depth=_depth + 1,
                )
            if hasattr(value, "model_dump"):
                try:
                    return self._coerce(
                        value.model_dump(),
                        _seen=_seen,
                        _depth=_depth + 1,
                    )
                except TypeError:
                    pass
            if is_dataclass(value):
                if isinstance(value, type):
                    return value.__name__
                return self._coerce(
                    asdict(value),
                    _seen=_seen,
                    _depth=_depth + 1,
                )
            if isinstance(value, (BaseMessage, BaseMessageChunk)):
                return {
                    "type": value.__class__.__name__,
                    "content": getattr(value, "content", None),
                    "additional_kwargs": getattr(value, "additional_kwargs", None),
                }
            if hasattr(value, "__dict__"):
                return {
                    str(k): self._coerce(v, _seen=_seen, _depth=_depth + 1)
                    for k, v in vars(value).items()
                }
            return repr(value)
        finally:
            if needs_tracking:
                _seen.discard(obj_id)

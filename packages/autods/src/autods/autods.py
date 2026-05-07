from __future__ import annotations

import asyncio
import json
import logging
import secrets
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessageChunk, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from autods.pipeline import build_pipeline
from autods.sessions import (
    SessionMetadata,
    SessionNotFoundError,
    SessionService,
    SessionStatus,
    SessionStorage,
    TranscriptMessage,
)

logger = logging.getLogger(__name__)

AutoDSEvent = dict[str, Any]
EventCallback = Callable[[AutoDSEvent], None]


def generate_principal_id() -> str:
    return secrets.token_urlsafe(24)


def _event(
    session_id: str,
    event_type: str,
    *,
    timestamp: str | None = None,
    message_id: str | None = None,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
    data: str | dict[str, Any] | None = None,
    tool_started_at: str | None = None,
    tool_completed_at: str | None = None,
    tool_duration_ms: int | None = None,
) -> AutoDSEvent:
    return {
        "type": event_type,
        "session_id": session_id,
        "message_id": message_id,
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "data": data,
        "tool_started_at": tool_started_at,
        "tool_completed_at": tool_completed_at,
        "tool_duration_ms": tool_duration_ms,
        "timestamp": timestamp or datetime.now(UTC).isoformat(),
    }


def _decode_tool_args(raw_args: str | None) -> dict[str, Any] | str:
    if raw_args is None:
        return {}
    stripped = raw_args.strip()
    if not stripped:
        return {}
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _format_tool_call_content(tool_name: str, args: dict[str, Any] | str) -> str:
    if isinstance(args, str):
        formatted_args = args
    else:
        formatted_args = json.dumps(args, ensure_ascii=False, indent=2).strip()
    return f"{tool_name}\n{formatted_args}".strip()


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_parts: list[str] = []
        image_count = 0
        for item in content:
            if isinstance(item, str):
                stripped = item.strip()
                if stripped:
                    text_parts.append(stripped)
                continue
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "text":
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    text_parts.append(text.strip())
            elif item_type == "image_url":
                image_count += 1
        if image_count:
            suffix = "s" if image_count != 1 else ""
            text_parts.append(f"[image output omitted: {image_count} image{suffix}]")
        return "\n".join(text_parts).strip()
    return str(content).strip()


def _tool_call_transcript_message(
    *,
    tool_call_id: str,
    tool_name: str,
    raw_args: str | None,
    started_at: datetime,
) -> TranscriptMessage:
    args = _decode_tool_args(raw_args)
    return TranscriptMessage(
        role="tool",
        content=tool_name,
        message_id=tool_call_id,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        tool_args=args,
        tool_status="running",
        tool_started_at=started_at,
    )


def _human_transcript_message(message: HumanMessage, *, user_prompt: str) -> TranscriptMessage | None:
    content = _message_content_to_text(message.content)
    if not content or content.strip() == user_prompt.strip():
        return None
    return TranscriptMessage(
        role="assistant",
        content=content,
        message_id=getattr(message, "id", None),
    )


def _tool_result_transcript_message(
    message: Any,
    *,
    tool_name: str | None = None,
    tool_args: dict[str, Any] | str | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> TranscriptMessage | None:
    content = _message_content_to_text(getattr(message, "content", ""))
    if not content:
        return None
    tool_call_id = getattr(message, "tool_call_id", None)
    if tool_call_id:
        completed_at = completed_at or datetime.now(UTC)
        duration_ms = (
            max(0, int((completed_at - started_at).total_seconds() * 1000))
            if started_at is not None
            else None
        )
        tool_status = "error" if getattr(message, "status", None) == "error" else "completed"
        return TranscriptMessage(
            role="tool",
            content=tool_name or "tool",
            message_id=tool_call_id,
            is_truncated=False,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=content,
            tool_status=tool_status,
            tool_started_at=started_at,
            tool_completed_at=completed_at,
            tool_duration_ms=duration_ms,
        )
    return TranscriptMessage(
        role="tool",
        content=content,
        message_id=getattr(message, "id", None),
        is_truncated=False,
    )


def _get_folder_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat(follow_symlinks=False).st_size
            except OSError as exc:
                logger.warning("Failed to stat %s: %s", entry, exc)
    return total


class _TranscriptRecorder:
    def __init__(
        self,
        service: SessionService,
        session: SessionMetadata,
        prompt: str,
        on_event: EventCallback | None,
    ) -> None:
        self.service = service
        self.session = session
        self.prompt = prompt
        self.on_event = on_event
        self.current_message_id: str | None = None
        self.current_assistant_chunks: list[str] = []
        self.started_tool_calls: set[str] = set()
        self.active_tool_calls: dict[str, dict[str, Any]] = {}
        self.tool_call_ids_by_index: dict[int, str] = {}

    def emit(
        self,
        event_type: str,
        *,
        timestamp: str | None = None,
        message_id: str | None = None,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        data: str | dict[str, Any] | None = None,
        tool_started_at: str | None = None,
        tool_completed_at: str | None = None,
        tool_duration_ms: int | None = None,
    ) -> None:
        if self.on_event is not None:
            self.on_event(
                _event(
                    self.session.id,
                    event_type,
                    timestamp=timestamp,
                    message_id=message_id,
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    data=data,
                    tool_started_at=tool_started_at,
                    tool_completed_at=tool_completed_at,
                    tool_duration_ms=tool_duration_ms,
                )
            )

    def finalize_assistant(self) -> None:
        if not self.current_assistant_chunks:
            return
        self.service.upsert_transcript_message(
            self.session.id,
            TranscriptMessage(
                role="assistant",
                content="".join(self.current_assistant_chunks),
                message_id=self.current_message_id,
                is_streaming=False,
            ),
        )
        self.current_message_id = None
        self.current_assistant_chunks = []

    def set_status(self, status: SessionStatus) -> None:
        try:
            self.service.set_status(self.session.id, status)
        except SessionNotFoundError:
            logger.debug("Skipping status update for deleted session %s", self.session.id)

    def fail(self, exc: Exception) -> None:
        self.finalize_assistant()
        self.set_status(SessionStatus.ERROR)
        error_message = f"Error: {exc}"
        try:
            self.service.append_transcript_message(
                self.session.id,
                TranscriptMessage(
                    role="tool",
                    content="run_failed",
                    tool_name="run_failed",
                    tool_result=error_message,
                    tool_status="error",
                ),
            )
        except SessionNotFoundError:
            logger.debug("Skipping error transcript append for deleted session %s", self.session.id)
        self.emit("run_failed", data=error_message)

    async def handle_stream_chunk(self, mode: str, chunk: Any) -> None:
        if mode != "messages":
            return
        message = chunk[0] if isinstance(chunk, tuple) else chunk
        if isinstance(message, AIMessageChunk):
            self._record_ai_chunk(message)
            return

        tool_call_id = getattr(message, "tool_call_id", None)
        active_tool_call = self.active_tool_calls.get(tool_call_id, {}) if tool_call_id else {}
        transcript_message = (
            _human_transcript_message(message, user_prompt=self.prompt)
            if isinstance(message, HumanMessage)
            else _tool_result_transcript_message(
                message,
                tool_name=active_tool_call.get("tool_name"),
                tool_args=active_tool_call.get("tool_args"),
                started_at=active_tool_call.get("started_at"),
                completed_at=datetime.now(UTC),
            )
        )
        if transcript_message is None:
            return

        self.finalize_assistant()
        if tool_call_id:
            self.service.upsert_transcript_message(self.session.id, transcript_message)
        else:
            self.service.append_transcript_message(self.session.id, transcript_message)
        self._emit_tool_result(message, transcript_message)

    def _record_ai_chunk(self, message: AIMessageChunk) -> None:
        incoming_id = (
            getattr(message, "id", None) or self.current_message_id or f"msg-{datetime.now(UTC).timestamp()}"
        )
        if self.current_message_id and incoming_id != self.current_message_id:
            self.finalize_assistant()
        self.current_message_id = incoming_id

        token = str(message.content or "")
        if token:
            self.current_assistant_chunks.append(token)
            self.service.upsert_transcript_message(
                self.session.id,
                TranscriptMessage(
                    role="assistant",
                    content="".join(self.current_assistant_chunks),
                    message_id=self.current_message_id,
                    timestamp=datetime.now(UTC),
                    is_streaming=True,
                ),
            )
            self.emit("assistant_text_delta", message_id=self.current_message_id, data=token)

        for tool_chunk in getattr(message, "tool_call_chunks", []):
            self._record_tool_call_chunk(tool_chunk)

    def _record_tool_call_chunk(self, tool_chunk: dict[str, Any]) -> None:
        tool_call_id = tool_chunk.get("id")
        chunk_index = tool_chunk.get("index")
        if not tool_call_id and isinstance(chunk_index, int):
            tool_call_id = self.tool_call_ids_by_index.get(chunk_index)
        if not tool_call_id:
            return
        if isinstance(chunk_index, int):
            self.tool_call_ids_by_index[chunk_index] = tool_call_id

        active = self.active_tool_calls.get(tool_call_id, {})
        tool_name = tool_chunk.get("name") or active.get("tool_name")
        if not tool_name:
            return

        raw_args = f"{active.get('raw_args') or ''}{tool_chunk.get('args') or ''}"
        args = _decode_tool_args(raw_args)
        started_at = active.get("started_at") or datetime.now(UTC)
        self.active_tool_calls[tool_call_id] = {
            "tool_name": tool_name,
            "message_id": active.get("message_id") or self.current_message_id,
            "raw_args": raw_args,
            "tool_args": args,
            "started_at": started_at,
        }
        self.service.upsert_transcript_message(
            self.session.id,
            _tool_call_transcript_message(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                raw_args=raw_args,
                started_at=started_at,
            ),
        )

        assistant_message_id = self.current_message_id
        if tool_call_id not in self.started_tool_calls:
            self.started_tool_calls.add(tool_call_id)
            if self.current_assistant_chunks:
                self.finalize_assistant()
        self.emit(
            "tool_call_started",
            message_id=assistant_message_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            data=args,
            tool_started_at=started_at.isoformat(),
        )

    def _emit_tool_result(self, message: Any, transcript_message: TranscriptMessage) -> None:
        tool_call_id = getattr(message, "tool_call_id", None)
        if not tool_call_id:
            return
        active = self.active_tool_calls.get(tool_call_id, {})
        self.emit(
            "tool_call_completed",
            timestamp=transcript_message.timestamp.isoformat(),
            message_id=active.get("message_id"),
            tool_call_id=tool_call_id,
            tool_name=active.get("tool_name"),
            tool_started_at=transcript_message.tool_started_at.isoformat()
            if transcript_message.tool_started_at is not None
            else None,
            tool_completed_at=transcript_message.tool_completed_at.isoformat()
            if transcript_message.tool_completed_at is not None
            else None,
            tool_duration_ms=transcript_message.tool_duration_ms,
            data={
                "output_text": transcript_message.tool_result or transcript_message.content,
                "is_truncated": transcript_message.is_truncated,
                "tool_status": transcript_message.tool_status,
            },
        )


class AutoDS:
    def __init__(self, *, root: str | Path | None = None) -> None:
        self.storage = SessionStorage(root=Path(root) if root is not None else None)
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}
        self._cancel_events: dict[str, threading.Event] = {}

    def _service(self, principal_id: str) -> SessionService:
        return SessionService(principal_id=principal_id, storage=self.storage)

    def list_sessions(self, principal_id: str) -> list[SessionMetadata]:
        return self._service(principal_id).list_sessions()

    def create_session(self, principal_id: str) -> SessionMetadata:
        return self._service(principal_id).create_session()

    def get_session(self, principal_id: str, session_id: str) -> SessionMetadata:
        return self._service(principal_id).get_session(session_id)

    def delete_session(self, principal_id: str, session_id: str) -> None:
        self._service(principal_id).delete_session(session_id)

    def list_transcript(self, principal_id: str, session_id: str) -> list[TranscriptMessage]:
        return self._service(principal_id).list_transcript_messages(session_id)

    def workspace_path(self, principal_id: str, session_id: str, *, create: bool = True) -> Path:
        return self._service(principal_id).workspace_path(session_id, create=create)

    def session_path(self, principal_id: str, session_id: str, *, create: bool = True) -> Path:
        return self._service(principal_id).session_path(session_id, create=create)

    def refresh_folder_size(self, principal_id: str, session_id: str) -> SessionMetadata:
        service = self._service(principal_id)
        workspace = service.workspace_path(session_id, create=False)
        return service.update_folder_size(session_id, _get_folder_size(workspace))

    def _refresh_folder_size_if_exists(self, principal_id: str, session_id: str) -> None:
        try:
            self.refresh_folder_size(principal_id, session_id)
        except SessionNotFoundError:
            logger.debug("Skipping workspace metadata sync for deleted session %s", session_id)
        except Exception:
            logger.exception("Failed to finalize workspace metadata for session %s", session_id)

    def start_run(
        self,
        principal_id: str,
        session_id: str,
        prompt: str,
        *,
        on_event: EventCallback | None = None,
    ) -> None:
        with self._lock:
            existing = self._threads.get(session_id)
            if existing and existing.is_alive():
                raise RuntimeError("Session already has a running task")
            cancel_event = threading.Event()
            self._cancel_events[session_id] = cancel_event

        service = self._service(principal_id)
        service.append_transcript_message(session_id, TranscriptMessage(role="user", content=prompt))
        service.set_status(session_id, SessionStatus.RUNNING)
        session = service.get_session(session_id)

        thread = threading.Thread(
            target=self._run_session,
            args=(session, prompt, cancel_event, on_event),
            daemon=True,
        )
        with self._lock:
            self._threads[session_id] = thread
        thread.start()

    def cancel_run(self, principal_id: str, session_id: str) -> bool:
        with self._lock:
            cancel_event = self._cancel_events.get(session_id)
        if cancel_event is None:
            return False
        cancel_event.set()
        self._service(principal_id).set_status(session_id, SessionStatus.CANCELLING)
        return True

    def wait_for_completion(self, session_id: str, timeout: float) -> None:
        with self._lock:
            thread = self._threads.get(session_id)
        if thread is not None:
            thread.join(timeout=timeout)

    def _run_session(
        self,
        session: SessionMetadata,
        prompt: str,
        cancel_event: threading.Event,
        on_event: EventCallback | None,
    ) -> None:
        service = self._service(session.principal_id)
        local_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(local_loop)
        recorder = _TranscriptRecorder(service, session, prompt, on_event)

        async def execute() -> None:
            try:
                recorder.emit("run_started")
                config: RunnableConfig = {
                    "recursion_limit": 200,
                    "configurable": {"thread_id": session.id},
                }
                stream_modes = ["values", "updates", "custom", "messages", "debug"]
                project_path = service.workspace_path(session.id).resolve()
                async with AsyncSqliteSaver.from_conn_string(session.checkpoint_nsp) as checkpointer:
                    pipeline = build_pipeline(str(project_path), checkpointer=checkpointer)
                    async for mode, chunk in pipeline.astream(
                        {"task": prompt},
                        config=config,
                        stream_mode=stream_modes,
                    ):
                        if cancel_event.is_set():
                            raise asyncio.CancelledError("Run cancelled")
                        await recorder.handle_stream_chunk(mode, chunk)
                recorder.finalize_assistant()
                recorder.set_status(SessionStatus.IDLE)
                recorder.emit("run_completed")
            except asyncio.CancelledError:
                recorder.finalize_assistant()
                recorder.set_status(SessionStatus.IDLE)
                recorder.emit("run_cancelled")
            except Exception as exc:
                logger.exception("Run failed for session %s", session.id)
                recorder.fail(exc)
            finally:
                self._refresh_folder_size_if_exists(session.principal_id, session.id)

        try:
            local_loop.run_until_complete(execute())
        except Exception as exc:
            logger.exception("Failed to initialize run for session %s", session.id)
            recorder.fail(exc)
        finally:
            with self._lock:
                self._cancel_events.pop(session.id, None)
                self._threads.pop(session.id, None)
            local_loop.close()

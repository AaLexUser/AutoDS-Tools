from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from pathlib import Path

from autods.sessions.domain import (
    CHECKPOINT_FILENAME,
    DATABASE_FILENAME,
    DEFAULT_SESSION_HOME,
    PRINCIPALS_DIRNAME,
    SESSION_HOME_ENV,
    SESSIONS_DIRNAME,
    TRACE_DIRNAME,
    WORKSPACE_DIRNAME,
    SessionMetadata,
    SessionNotFoundError,
    SessionOwnershipError,
    TranscriptMessage,
    validate_principal_id,
)

logger = logging.getLogger(__name__)


class SessionStorage:
    """SQLite-backed metadata storage with filesystem-backed session paths."""

    def __init__(self, root: Path | None = None) -> None:
        desired_root = root or Path(os.environ.get(SESSION_HOME_ENV, DEFAULT_SESSION_HOME))
        self.root = self._prepare_root(desired_root)
        self.database_path = self.root / DATABASE_FILENAME
        self.principals_root = self._ensure_dir(self.root / PRINCIPALS_DIRNAME)
        self._lock = threading.RLock()
        self._initialize_schema()

    def _prepare_root(self, candidate: Path) -> Path:
        candidate = candidate.expanduser()
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate.resolve()
        except PermissionError:
            fallback = Path.cwd() / ".autods" / "sessions"
            fallback.mkdir(parents=True, exist_ok=True)
            logger.warning(
                "Falling back to %s for session storage (permission denied for %s)",
                fallback,
                candidate,
            )
            return fallback.resolve()

    def _ensure_dir(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_schema(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    principal_id TEXT NOT NULL,
                    checkpoint_nsp TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    folder_size INTEGER NOT NULL DEFAULT 0,
                    title TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_principal_updated
                ON sessions (principal_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS transcript_messages (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    message_id TEXT,
                    is_truncated INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_transcript_session_seq
                ON transcript_messages (session_id, seq);
                """
            )
            transcript_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(transcript_messages)").fetchall()
            }
            if "is_streaming" not in transcript_columns:
                connection.execute(
                    """
                    ALTER TABLE transcript_messages
                    ADD COLUMN is_streaming INTEGER NOT NULL DEFAULT 0
                    """
                )
            for column in (
                "tool_call_id",
                "tool_name",
                "tool_args",
                "tool_result",
                "tool_status",
                "tool_started_at",
                "tool_completed_at",
            ):
                if column not in transcript_columns:
                    connection.execute(f"ALTER TABLE transcript_messages ADD COLUMN {column} TEXT")
            if "tool_duration_ms" not in transcript_columns:
                connection.execute("ALTER TABLE transcript_messages ADD COLUMN tool_duration_ms INTEGER")

    def principal_path(self, principal_id: str, *, create: bool = True) -> Path:
        path = self.principals_root / validate_principal_id(principal_id)
        return self._ensure_dir(path) if create else path

    def session_path(self, principal_id: str, session_id: str, *, create: bool = True) -> Path:
        path = self.principal_path(principal_id, create=create) / SESSIONS_DIRNAME / session_id
        return self._ensure_dir(path) if create else path

    def workspace_path(self, principal_id: str, session_id: str, *, create: bool = True) -> Path:
        path = self.session_path(principal_id, session_id, create=create) / WORKSPACE_DIRNAME
        return self._ensure_dir(path) if create else path

    def trace_path(self, principal_id: str, session_id: str, *, create: bool = True) -> Path:
        path = self.session_path(principal_id, session_id, create=create) / TRACE_DIRNAME
        return self._ensure_dir(path) if create else path

    def checkpoint_path(self, principal_id: str, session_id: str) -> Path:
        return self.session_path(principal_id, session_id) / CHECKPOINT_FILENAME

    def list_sessions(self, principal_id: str) -> list[SessionMetadata]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, principal_id, checkpoint_nsp, created_at, updated_at, status,
                       folder_size, title
                FROM sessions
                WHERE principal_id = ?
                ORDER BY updated_at DESC
                """,
                (principal_id,),
            ).fetchall()
        return [SessionMetadata.model_validate(dict(row)) for row in rows]

    def create_session(self, session: SessionMetadata) -> SessionMetadata:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (
                    id, principal_id, checkpoint_nsp, created_at, updated_at, status,
                    folder_size, title
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.id,
                    session.principal_id,
                    session.checkpoint_nsp,
                    session.created_at.isoformat(),
                    session.updated_at.isoformat(),
                    session.status,
                    session.folder_size,
                    session.title,
                ),
            )
        return session

    def get_session(self, principal_id: str, session_id: str) -> SessionMetadata:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, principal_id, checkpoint_nsp, created_at, updated_at, status,
                       folder_size, title
                FROM sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()

        if row is None:
            raise SessionNotFoundError(session_id)

        session = SessionMetadata.model_validate(dict(row))
        if session.principal_id != principal_id:
            raise SessionOwnershipError(session_id)
        return session

    def save_session(self, session: SessionMetadata) -> SessionMetadata:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE sessions
                SET updated_at = ?, status = ?, folder_size = ?, title = ?, checkpoint_nsp = ?
                WHERE id = ? AND principal_id = ?
                """,
                (
                    session.updated_at.isoformat(),
                    session.status,
                    session.folder_size,
                    session.title,
                    session.checkpoint_nsp,
                    session.id,
                    session.principal_id,
                ),
            )
        return session

    def delete_session(self, principal_id: str, session_id: str) -> None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT principal_id FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise SessionNotFoundError(session_id)
            if row["principal_id"] != principal_id:
                raise SessionOwnershipError(session_id)
            connection.execute(
                "DELETE FROM transcript_messages WHERE session_id = ?",
                (session_id,),
            )
            connection.execute(
                "DELETE FROM sessions WHERE id = ?",
                (session_id,),
            )

    def append_transcript_message(
        self, principal_id: str, session_id: str, message: TranscriptMessage
    ) -> TranscriptMessage:
        self.get_session(principal_id, session_id)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO transcript_messages (
                    session_id, role, content, timestamp, message_id, is_truncated,
                    is_streaming, tool_call_id, tool_name, tool_args, tool_result, tool_status,
                    tool_started_at, tool_completed_at, tool_duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    message.role,
                    message.content,
                    message.timestamp.isoformat(),
                    message.message_id,
                    int(message.is_truncated),
                    int(message.is_streaming),
                    message.tool_call_id,
                    message.tool_name,
                    json.dumps(message.tool_args, ensure_ascii=False) if message.tool_args is not None else None,
                    message.tool_result,
                    message.tool_status,
                    message.tool_started_at.isoformat() if message.tool_started_at is not None else None,
                    message.tool_completed_at.isoformat() if message.tool_completed_at is not None else None,
                    message.tool_duration_ms,
                ),
            )
        return message

    def upsert_transcript_message(
        self, principal_id: str, session_id: str, message: TranscriptMessage
    ) -> TranscriptMessage:
        if message.message_id is None:
            return self.append_transcript_message(principal_id, session_id, message)

        self.get_session(principal_id, session_id)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT seq
                FROM transcript_messages
                WHERE session_id = ? AND message_id = ?
                ORDER BY seq ASC
                LIMIT 1
                """,
                (session_id, message.message_id),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO transcript_messages (
                        session_id, role, content, timestamp, message_id,
                        is_truncated, is_streaming, tool_call_id, tool_name, tool_args,
                        tool_result, tool_status, tool_started_at, tool_completed_at,
                        tool_duration_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        message.role,
                        message.content,
                        message.timestamp.isoformat(),
                        message.message_id,
                        int(message.is_truncated),
                        int(message.is_streaming),
                        message.tool_call_id,
                        message.tool_name,
                        json.dumps(message.tool_args, ensure_ascii=False) if message.tool_args is not None else None,
                        message.tool_result,
                        message.tool_status,
                        message.tool_started_at.isoformat() if message.tool_started_at is not None else None,
                        message.tool_completed_at.isoformat() if message.tool_completed_at is not None else None,
                        message.tool_duration_ms,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE transcript_messages
                    SET role = ?, content = ?, timestamp = ?, is_truncated = ?,
                        is_streaming = ?, tool_call_id = ?, tool_name = ?, tool_args = ?,
                        tool_result = ?, tool_status = ?, tool_started_at = ?,
                        tool_completed_at = ?, tool_duration_ms = ?
                    WHERE seq = ?
                    """,
                    (
                        message.role,
                        message.content,
                        message.timestamp.isoformat(),
                        int(message.is_truncated),
                        int(message.is_streaming),
                        message.tool_call_id,
                        message.tool_name,
                        json.dumps(message.tool_args, ensure_ascii=False) if message.tool_args is not None else None,
                        message.tool_result,
                        message.tool_status,
                        message.tool_started_at.isoformat() if message.tool_started_at is not None else None,
                        message.tool_completed_at.isoformat() if message.tool_completed_at is not None else None,
                        message.tool_duration_ms,
                        row["seq"],
                    ),
                )
        return message

    def list_transcript_messages(self, principal_id: str, session_id: str) -> list[TranscriptMessage]:
        self.get_session(principal_id, session_id)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT role, content, timestamp, message_id, is_truncated,
                       is_streaming, tool_call_id, tool_name, tool_args, tool_result,
                       tool_status, tool_started_at, tool_completed_at, tool_duration_ms
                FROM transcript_messages
                WHERE session_id = ?
                ORDER BY seq ASC
                """,
                (session_id,),
            ).fetchall()
        messages: list[TranscriptMessage] = []
        for row in rows:
            values = dict(row)
            raw_tool_args = values.get("tool_args")
            if raw_tool_args is not None:
                try:
                    values["tool_args"] = json.loads(raw_tool_args)
                except json.JSONDecodeError:
                    values["tool_args"] = raw_tool_args
            values["is_truncated"] = bool(row["is_truncated"])
            values["is_streaming"] = bool(row["is_streaming"])
            messages.append(TranscriptMessage.model_validate(values))
        return messages

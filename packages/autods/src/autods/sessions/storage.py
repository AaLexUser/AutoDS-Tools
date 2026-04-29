from __future__ import annotations

import logging
import os
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from autods.auth import AuditLogEntry, AuthUser, CliTokenRecord, UserStatus
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
        desired_root = root or Path(
            os.environ.get(SESSION_HOME_ENV, DEFAULT_SESSION_HOME)
        )
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

                CREATE TABLE IF NOT EXISTS auth_users (
                    id TEXT PRIMARY KEY,
                    workos_user_id TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL UNIQUE,
                    display_name TEXT,
                    status TEXT NOT NULL,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    approved_at TEXT,
                    approved_by TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_auth_users_email
                ON auth_users (email);

                CREATE TABLE IF NOT EXISTS cli_tokens (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    label TEXT,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    expires_at TEXT,
                    revoked_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_cli_tokens_user_id
                ON cli_tokens (user_id);

                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY,
                    actor_user_id TEXT,
                    action TEXT NOT NULL,
                    target_user_id TEXT,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            transcript_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(transcript_messages)"
                ).fetchall()
            }
            if "is_streaming" not in transcript_columns:
                connection.execute(
                    """
                    ALTER TABLE transcript_messages
                    ADD COLUMN is_streaming INTEGER NOT NULL DEFAULT 0
                    """
                )

    def _row_to_auth_user(self, row: sqlite3.Row) -> AuthUser:
        return AuthUser.model_validate(
            {
                **dict(row),
                "is_admin": bool(row["is_admin"]),
            }
        )

    def _row_to_cli_token(self, row: sqlite3.Row) -> CliTokenRecord:
        return CliTokenRecord.model_validate(dict(row))

    def _get_auth_user_row_by_workos_id(
        self,
        connection: sqlite3.Connection,
        workos_user_id: str,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT id, workos_user_id, email, display_name, status, is_admin,
                   created_at, updated_at, approved_at, approved_by
            FROM auth_users
            WHERE workos_user_id = ?
            LIMIT 1
            """,
            (workos_user_id,),
        ).fetchone()

    def _get_auth_user_row_by_email(
        self,
        connection: sqlite3.Connection,
        email: str,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT id, workos_user_id, email, display_name, status, is_admin,
                   created_at, updated_at, approved_at, approved_by
            FROM auth_users
            WHERE email = ?
            LIMIT 1
            """,
            (email,),
        ).fetchone()

    def principal_path(self, principal_id: str, *, create: bool = True) -> Path:
        path = self.principals_root / validate_principal_id(principal_id)
        return self._ensure_dir(path) if create else path

    def session_path(
        self, principal_id: str, session_id: str, *, create: bool = True
    ) -> Path:
        path = (
            self.principal_path(principal_id, create=create)
            / SESSIONS_DIRNAME
            / session_id
        )
        return self._ensure_dir(path) if create else path

    def workspace_path(
        self, principal_id: str, session_id: str, *, create: bool = True
    ) -> Path:
        path = (
            self.session_path(principal_id, session_id, create=create)
            / WORKSPACE_DIRNAME
        )
        return self._ensure_dir(path) if create else path

    def trace_path(
        self, principal_id: str, session_id: str, *, create: bool = True
    ) -> Path:
        path = (
            self.session_path(principal_id, session_id, create=create) / TRACE_DIRNAME
        )
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
                    is_streaming
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    message.role,
                    message.content,
                    message.timestamp.isoformat(),
                    message.message_id,
                    int(message.is_truncated),
                    int(message.is_streaming),
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
                        is_truncated, is_streaming
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        message.role,
                        message.content,
                        message.timestamp.isoformat(),
                        message.message_id,
                        int(message.is_truncated),
                        int(message.is_streaming),
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE transcript_messages
                    SET role = ?, content = ?, timestamp = ?, is_truncated = ?,
                        is_streaming = ?
                    WHERE seq = ?
                    """,
                    (
                        message.role,
                        message.content,
                        message.timestamp.isoformat(),
                        int(message.is_truncated),
                        int(message.is_streaming),
                        row["seq"],
                    ),
                )
        return message

    def list_transcript_messages(
        self, principal_id: str, session_id: str
    ) -> list[TranscriptMessage]:
        self.get_session(principal_id, session_id)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT role, content, timestamp, message_id, is_truncated,
                       is_streaming
                FROM transcript_messages
                WHERE session_id = ?
                ORDER BY seq ASC
                """,
                (session_id,),
            ).fetchall()
        return [
            TranscriptMessage.model_validate(
                {
                    **dict(row),
                    "is_truncated": bool(row["is_truncated"]),
                    "is_streaming": bool(row["is_streaming"]),
                }
            )
            for row in rows
        ]

    def upsert_auth_user(
        self,
        *,
        workos_user_id: str,
        email: str,
        display_name: str | None = None,
        bootstrap_admin_emails: set[str] | None = None,
    ) -> AuthUser:
        normalized_email = email.strip().lower()
        bootstrap_admin = normalized_email in (bootstrap_admin_emails or set())
        now = datetime.now(UTC)

        with self._lock, self._connect() as connection:
            workos_row = self._get_auth_user_row_by_workos_id(
                connection,
                workos_user_id,
            )
            email_row = self._get_auth_user_row_by_email(connection, normalized_email)

            if workos_row is None and email_row is None:
                user = AuthUser(
                    id=uuid.uuid4().hex,
                    workos_user_id=workos_user_id,
                    email=normalized_email,
                    display_name=display_name,
                    status=UserStatus.APPROVED if bootstrap_admin else UserStatus.PENDING,
                    is_admin=bootstrap_admin,
                    approved_at=now if bootstrap_admin else None,
                )
                connection.execute(
                    """
                    INSERT INTO auth_users (
                        id, workos_user_id, email, display_name, status, is_admin,
                        created_at, updated_at, approved_at, approved_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user.id,
                        user.workos_user_id,
                        user.email,
                        user.display_name,
                        user.status,
                        int(user.is_admin),
                        user.created_at.isoformat(),
                        user.updated_at.isoformat(),
                        user.approved_at.isoformat() if user.approved_at else None,
                        user.approved_by,
                    ),
                )
                return user

            row = workos_row or email_row
            assert row is not None
            user = self._row_to_auth_user(row)

            if workos_row is None and workos_user_id and user.workos_user_id != workos_user_id:
                user.workos_user_id = workos_user_id

            if email_row is None or email_row["id"] == user.id:
                user.email = normalized_email

            user.display_name = display_name
            user.updated_at = now
            if bootstrap_admin:
                user.is_admin = True
                user.status = UserStatus.APPROVED
                user.approved_at = user.approved_at or now
            connection.execute(
                """
                UPDATE auth_users
                SET workos_user_id = ?, email = ?, display_name = ?, status = ?,
                    is_admin = ?, updated_at = ?, approved_at = ?, approved_by = ?
                WHERE id = ?
                """,
                (
                    user.workos_user_id,
                    user.email,
                    user.display_name,
                    user.status,
                    int(user.is_admin),
                    user.updated_at.isoformat(),
                    user.approved_at.isoformat() if user.approved_at else None,
                    user.approved_by,
                    user.id,
                ),
            )
            return user

    def get_auth_user_by_id(self, user_id: str) -> AuthUser:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, workos_user_id, email, display_name, status, is_admin,
                       created_at, updated_at, approved_at, approved_by
                FROM auth_users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            raise SessionNotFoundError(user_id)
        return self._row_to_auth_user(row)

    def get_auth_user_by_workos_id(self, workos_user_id: str) -> AuthUser:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, workos_user_id, email, display_name, status, is_admin,
                       created_at, updated_at, approved_at, approved_by
                FROM auth_users
                WHERE workos_user_id = ?
                """,
                (workos_user_id,),
            ).fetchone()
        if row is None:
            raise SessionNotFoundError(workos_user_id)
        return self._row_to_auth_user(row)

    def list_auth_users(self) -> list[AuthUser]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, workos_user_id, email, display_name, status, is_admin,
                       created_at, updated_at, approved_at, approved_by
                FROM auth_users
                ORDER BY created_at ASC
                """
            ).fetchall()
        return [self._row_to_auth_user(row) for row in rows]

    def set_auth_user_status(
        self,
        user_id: str,
        *,
        status: UserStatus,
        approved_by: str | None = None,
    ) -> AuthUser:
        user = self.get_auth_user_by_id(user_id)
        user.status = status
        user.updated_at = datetime.now(UTC)
        if status == UserStatus.APPROVED:
            user.approved_at = user.updated_at
            user.approved_by = approved_by
        connection_values = (
            user.status,
            user.updated_at.isoformat(),
            user.approved_at.isoformat() if user.approved_at else None,
            user.approved_by,
            user.id,
        )
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE auth_users
                SET status = ?, updated_at = ?, approved_at = ?, approved_by = ?
                WHERE id = ?
                """,
                connection_values,
            )
        return user

    def create_cli_token(
        self,
        *,
        user_id: str,
        token_hash: str,
        label: str | None = None,
        expires_at: datetime | None = None,
    ) -> CliTokenRecord:
        token = CliTokenRecord(
            id=uuid.uuid4().hex,
            user_id=user_id,
            token_hash=token_hash,
            label=label,
            expires_at=expires_at,
        )
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO cli_tokens (
                    id, user_id, token_hash, label, created_at, last_used_at,
                    expires_at, revoked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token.id,
                    token.user_id,
                    token.token_hash,
                    token.label,
                    token.created_at.isoformat(),
                    token.last_used_at.isoformat() if token.last_used_at else None,
                    token.expires_at.isoformat() if token.expires_at else None,
                    token.revoked_at.isoformat() if token.revoked_at else None,
                ),
            )
        return token

    def list_cli_tokens(self, user_id: str) -> list[CliTokenRecord]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, user_id, token_hash, label, created_at, last_used_at,
                       expires_at, revoked_at
                FROM cli_tokens
                WHERE user_id = ? AND revoked_at IS NULL
                ORDER BY created_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [self._row_to_cli_token(row) for row in rows]

    def get_cli_token(self, token_hash: str) -> CliTokenRecord | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, user_id, token_hash, label, created_at, last_used_at,
                       expires_at, revoked_at
                FROM cli_tokens
                WHERE token_hash = ? AND revoked_at IS NULL
                """,
                (token_hash,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_cli_token(row)

    def touch_cli_token(self, token_id: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE cli_tokens
                SET last_used_at = ?
                WHERE id = ? AND revoked_at IS NULL
                """,
                (datetime.now(UTC).isoformat(), token_id),
            )

    def revoke_cli_token(self, user_id: str, token_id: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE cli_tokens
                SET revoked_at = ?
                WHERE id = ? AND user_id = ? AND revoked_at IS NULL
                """,
                (datetime.now(UTC).isoformat(), token_id, user_id),
            )

    def append_audit_log(
        self,
        *,
        action: str,
        actor_user_id: str | None = None,
        target_user_id: str | None = None,
        metadata_json: str | None = None,
    ) -> AuditLogEntry:
        entry = AuditLogEntry(
            id=uuid.uuid4().hex,
            actor_user_id=actor_user_id,
            action=action,
            target_user_id=target_user_id,
            metadata_json=metadata_json,
        )
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_log (
                    id, actor_user_id, action, target_user_id, metadata_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.actor_user_id,
                    entry.action,
                    entry.target_user_id,
                    entry.metadata_json,
                    entry.created_at.isoformat(),
                ),
            )
        return entry

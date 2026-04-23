from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from autods.sessions.domain import SessionMetadata, SessionStatus, TranscriptMessage
from autods.sessions.storage import SessionStorage


def _generate_session_id() -> str:
    now = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    slug = uuid.uuid4().hex[:8]
    return f"{now}-{slug}"


class SessionService:
    def __init__(
        self,
        principal_id: str,
        storage: SessionStorage | None = None,
        root: Path | None = None,
    ) -> None:
        self.principal_id = principal_id
        self.storage = storage or SessionStorage(root=root)

    def list_sessions(self) -> list[SessionMetadata]:
        return self.storage.list_sessions(self.principal_id)

    def create_session(self, id: str | None = None) -> SessionMetadata:
        new_session_id = id or _generate_session_id()
        checkpoint_path = self.storage.checkpoint_path(
            self.principal_id, new_session_id
        )
        metadata = SessionMetadata(
            id=new_session_id,
            principal_id=self.principal_id,
            checkpoint_nsp=str(checkpoint_path),
        )
        self.storage.workspace_path(self.principal_id, new_session_id)
        self.storage.trace_path(self.principal_id, new_session_id)
        return self.storage.create_session(metadata)

    def get_session(self, id: str) -> SessionMetadata:
        return self.storage.get_session(self.principal_id, id)

    def upsert_session(self, metadata: SessionMetadata) -> SessionMetadata:
        metadata.touch()
        return self.storage.save_session(metadata)

    def delete_session(self, id: str) -> None:
        self.storage.delete_session(self.principal_id, id)

    def update_folder_size(self, id: str, size: int) -> SessionMetadata:
        metadata = self.get_session(id)
        metadata.folder_size = size
        return self.upsert_session(metadata)

    def set_status(self, id: str, status: SessionStatus | str) -> SessionMetadata:
        metadata = self.get_session(id)
        metadata.status = SessionStatus(status)
        return self.upsert_session(metadata)

    def append_transcript_message(
        self, id: str, message: TranscriptMessage
    ) -> TranscriptMessage:
        return self.storage.append_transcript_message(self.principal_id, id, message)

    def upsert_transcript_message(
        self, id: str, message: TranscriptMessage
    ) -> TranscriptMessage:
        return self.storage.upsert_transcript_message(self.principal_id, id, message)

    def list_transcript_messages(self, id: str) -> list[TranscriptMessage]:
        return self.storage.list_transcript_messages(self.principal_id, id)

    def workspace_path(self, id: str, *, create: bool = True) -> Path:
        self.get_session(id)
        return self.storage.workspace_path(self.principal_id, id, create=create)

    def trace_path(self, id: str) -> Path:
        self.get_session(id)
        return self.storage.trace_path(self.principal_id, id)

    def session_path(self, id: str, *, create: bool = True) -> Path:
        self.get_session(id)
        return self.storage.session_path(self.principal_id, id, create=create)

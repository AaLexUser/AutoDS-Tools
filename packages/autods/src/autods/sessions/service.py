import uuid
from datetime import datetime
from typing import List

from autods.sessions.domain import (
    SessionManifest,
    SessionMetadata,
    SessionNotFoundError,
)
from autods.sessions.storage import SessionStorage


def _generate_session_id() -> str:
    now = datetime.now().strftime("%Y%m%d-%H%M")
    slug = uuid.uuid4().hex[:8]
    return f"{now}-{slug}"


class SessionService:
    def __init__(self, storage: SessionStorage | None = None) -> None:
        self.storage = storage or SessionStorage()

    def _load_manifest(self) -> SessionManifest:
        return self.storage.load_manifest()

    def _save_manifest(self, manifest: SessionManifest) -> None:
        self.storage.save_manifest(manifest)

    def list_sessions(self) -> List[SessionMetadata]:
        manifest = self._load_manifest()
        sessions = list(manifest.sessions.values())
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    def create_session(self, id: str | None = None) -> SessionMetadata:
        manifest = self._load_manifest()
        new_session_id = id or _generate_session_id()
        metadata = SessionMetadata(
            id=new_session_id, checkpoint_nsp=str(self.storage.checkpoint_path())
        )
        manifest.sessions[new_session_id] = metadata
        self._save_manifest(manifest)
        return metadata

    def get_session(self, id: str) -> SessionMetadata:
        manifest = self._load_manifest()
        metadata = manifest.sessions.get(id)
        if metadata is None:
            raise SessionNotFoundError(id)
        return metadata

    def upsert_session(self, metadata: SessionMetadata) -> SessionMetadata:
        manifest = self._load_manifest()
        metadata.touch()
        manifest.sessions[metadata.id] = metadata
        self._save_manifest(manifest)
        return metadata

    def delete_session(self, id: str) -> None:
        manifest = self._load_manifest()
        if id not in manifest.sessions:
            raise SessionNotFoundError(id)
        del manifest.sessions[id]
        self._save_manifest(manifest)

    def update_folder_size(self, id: str, size: int) -> None:
        """Update the cached folder size for a session."""
        manifest = self._load_manifest()
        if id not in manifest.sessions:
            raise SessionNotFoundError(id)
        manifest.sessions[id].folder_size = size
        self._save_manifest(manifest)

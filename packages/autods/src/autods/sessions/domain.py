from datetime import datetime

from pydantic import BaseModel, Field

from autods.constants import AUTODS_HOME

SESSION_HOME_ENV = "AUTODS_SESSION_HOME"
DEFAULT_SESSION_HOME = AUTODS_HOME / "sessions"
CHECKPOINTS_DIRNAME = "checkpoints"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_VERSION = 1


class ManifestStorageError(RuntimeError):
    pass


class SessionNotFoundError(KeyError):
    pass


class SessionMetadata(BaseModel):
    id: str
    checkpoint_nsp: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    folder_size: int = 0  # Cached folder size in bytes

    def touch(self) -> None:
        self.updated_at = datetime.now()


class SessionManifest(BaseModel):
    version: int = MANIFEST_VERSION
    sessions: dict[str, SessionMetadata] = Field(default_factory=dict)

    @classmethod
    def empty(cls) -> "SessionManifest":
        return cls(version=MANIFEST_VERSION, sessions={})

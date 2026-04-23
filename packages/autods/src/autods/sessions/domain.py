from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from autods.constants import AUTODS_HOME

SESSION_HOME_ENV = "AUTODS_SESSION_HOME"
DEFAULT_SESSION_HOME = AUTODS_HOME / "sessions"
DATABASE_FILENAME = "sessions.sqlite3"
PRINCIPALS_DIRNAME = "principals"
SESSIONS_DIRNAME = "sessions"
WORKSPACE_DIRNAME = "workspace"
TRACE_DIRNAME = "trace"
CHECKPOINT_FILENAME = "checkpoint.sqlite"
PRINCIPAL_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class SessionStorageError(RuntimeError):
    pass


class SessionNotFoundError(KeyError):
    pass


class SessionOwnershipError(PermissionError):
    pass


class SessionStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    CANCELLING = "cancelling"
    ERROR = "error"


class SessionMetadata(BaseModel):
    id: str
    principal_id: str
    checkpoint_nsp: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: SessionStatus = SessionStatus.IDLE
    folder_size: int = 0
    title: str | None = None

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC)


class TranscriptMessage(BaseModel):
    role: Literal["user", "assistant", "environment"]
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    message_id: str | None = None
    is_truncated: bool = False
    is_streaming: bool = False


def validate_principal_id(principal_id: str) -> str:
    if not PRINCIPAL_ID_PATTERN.fullmatch(principal_id):
        raise SessionStorageError("Invalid principal identity")
    return principal_id

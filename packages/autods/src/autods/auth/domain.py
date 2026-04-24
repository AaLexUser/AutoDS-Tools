from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class UserStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DISABLED = "disabled"


class AuthUser(BaseModel):
    id: str
    workos_user_id: str
    email: str
    display_name: str | None = None
    status: UserStatus = UserStatus.PENDING
    is_admin: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    approved_at: datetime | None = None
    approved_by: str | None = None


class CliTokenRecord(BaseModel):
    id: str
    user_id: str
    token_hash: str
    label: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None


class AuditLogEntry(BaseModel):
    id: str
    actor_user_id: str | None = None
    action: str
    target_user_id: str | None = None
    metadata_json: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from cryptography.fernet import Fernet
from fastapi import HTTPException, Request
from workos.session import seal_session_from_auth_response

from autods.auth import AuthUser, UserStatus
from autods.sessions import SessionStorage

WORKOS_SESSION_COOKIE_NAME = "autods_wos_session"


@dataclass(frozen=True)
class AuthSettings:
    mode: str
    workos_client_id: str | None
    workos_api_key: str | None
    workos_redirect_uri: str | None
    cookie_password: str | None
    bootstrap_admin_emails: frozenset[str]
    auth_cookie_secure: bool
    cli_token_secret: str | None

    @classmethod
    def from_env(cls) -> "AuthSettings":
        bootstrap = {
            item.strip().lower()
            for item in os.environ.get("AUTH_BOOTSTRAP_ADMIN_EMAILS", "").split(",")
            if item.strip()
        }
        auth_secret = os.environ.get("AUTH_SECRET")
        return cls(
            mode=os.environ.get("AUTH_MODE", "disabled").strip().lower() or "disabled",
            workos_client_id=os.environ.get("WORKOS_CLIENT_ID"),
            workos_api_key=os.environ.get("WORKOS_API_KEY"),
            workos_redirect_uri=os.environ.get("WORKOS_REDIRECT_URI"),
            cookie_password=_normalize_cookie_password(
                os.environ.get("WORKOS_COOKIE_PASSWORD") or auth_secret
            ),
            bootstrap_admin_emails=frozenset(bootstrap),
            auth_cookie_secure=os.environ.get("AUTH_COOKIE_SECURE", "false").lower()
            == "true",
            cli_token_secret=os.environ.get("CLI_TOKEN_SECRET") or auth_secret,
        )

    @property
    def enabled(self) -> bool:
        return self.mode == "workos"

    @property
    def frontend_root_url(self) -> str:
        redirect_uri = self.workos_redirect_uri or "http://localhost:3000/api/auth/callback"
        parts = urlsplit(redirect_uri)
        return urlunsplit((parts.scheme, parts.netloc, "/", "", ""))


@dataclass(frozen=True)
class WorkOSIdentity:
    workos_user_id: str
    email: str
    display_name: str | None


class WorkOSAuthManager:
    def __init__(
        self,
        storage: SessionStorage,
        settings: AuthSettings | None = None,
        workos_client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.storage = storage
        self.settings = settings or AuthSettings.from_env()
        self._workos_client_factory = workos_client_factory
        self._workos_client: Any | None = None

    def _get_workos_client(self) -> Any:
        if self._workos_client is None:
            if self._workos_client_factory is not None:
                self._workos_client = self._workos_client_factory()
            else:
                from workos import WorkOSClient

                if not self.settings.workos_api_key or not self.settings.workos_client_id:
                    raise RuntimeError("Missing WorkOS credentials")
                self._workos_client = WorkOSClient(
                    api_key=self.settings.workos_api_key,
                    client_id=self.settings.workos_client_id,
                )
        return self._workos_client

    def ensure_enabled(self) -> None:
        if not self.settings.enabled:
            raise HTTPException(status_code=404, detail="Auth mode disabled")
        if not self.settings.cookie_password:
            raise RuntimeError("Missing WORKOS_COOKIE_PASSWORD or AUTH_SECRET")

    def _user_from_identity(self, identity: WorkOSIdentity) -> AuthUser:
        return self.storage.upsert_auth_user(
            workos_user_id=identity.workos_user_id,
            email=identity.email,
            display_name=identity.display_name,
            bootstrap_admin_emails=set(self.settings.bootstrap_admin_emails),
        )

    def build_login_url(self) -> str:
        self.ensure_enabled()
        client = self._get_workos_client()
        return client.user_management.get_authorization_url(
            provider="authkit",
            redirect_uri=self.settings.workos_redirect_uri,
        )

    def exchange_code(self, code: str | None) -> tuple[AuthUser, str]:
        self.ensure_enabled()
        if not code:
            raise HTTPException(status_code=400, detail="Missing code")
        client = self._get_workos_client()
        auth_response = client.user_management.authenticate_with_code(code=code)
        user_obj = auth_response.user
        cookie_password = self.settings.cookie_password
        user_payload = _serialize_workos_value(user_obj)
        if cookie_password is None or user_payload is None:
            raise RuntimeError("Failed to build WorkOS session cookie")
        sealed_session = seal_session_from_auth_response(
            access_token=auth_response.access_token,
            refresh_token=auth_response.refresh_token,
            user=user_payload,
            impersonator=_serialize_workos_value(
                getattr(auth_response, "impersonator", None)
            ),
            cookie_password=cookie_password,
        )
        identity = self._identity_from_user(user_obj)
        user = self._user_from_identity(identity)
        self.storage.append_audit_log(
            action="auth.login",
            actor_user_id=user.id,
            target_user_id=user.id,
        )
        return user, sealed_session

    def authenticate_browser_user(self, sealed_session: str | None) -> AuthUser | None:
        self.ensure_enabled()
        if not sealed_session:
            return None
        client = self._get_workos_client()
        session = client.user_management.load_sealed_session(
            session_data=sealed_session,
            cookie_password=self.settings.cookie_password,
        )
        response = session.authenticate()
        if not getattr(response, "authenticated", False) or getattr(response, "user", None) is None:
            return None
        return self._user_from_identity(self._identity_from_user(response.user))

    def logout_url(self, sealed_session: str | None) -> str:
        self.ensure_enabled()
        if not sealed_session:
            return self.settings.frontend_root_url
        client = self._get_workos_client()
        session = client.user_management.load_sealed_session(
            session_data=sealed_session,
            cookie_password=self.settings.cookie_password,
        )
        return session.get_logout_url()

    def resolve_browser_user(self, request: Request) -> AuthUser | None:
        if not self.settings.enabled:
            return None
        return self.authenticate_browser_user(
            request.cookies.get(WORKOS_SESSION_COOKIE_NAME)
        )

    def resolve_cli_user(self, bearer_token: str | None) -> AuthUser | None:
        if not self.settings.enabled or not bearer_token or not self.settings.cli_token_secret:
            return None
        token_hash = self.hash_cli_token(bearer_token, self.settings.cli_token_secret)
        record = self.storage.get_cli_token(token_hash)
        if record is None:
            return None
        if record.expires_at is not None and record.expires_at <= datetime.now(UTC):
            return None
        self.storage.touch_cli_token(record.id)
        return self.storage.get_auth_user_by_id(record.user_id)

    def create_cli_token(self, user_id: str, *, label: str | None = None) -> tuple[str, str]:
        if not self.settings.cli_token_secret:
            raise RuntimeError("Missing CLI_TOKEN_SECRET or AUTH_SECRET")
        raw_token = f"autods_{secrets.token_urlsafe(32)}"
        token_hash = self.hash_cli_token(raw_token, self.settings.cli_token_secret)
        record = self.storage.create_cli_token(
            user_id=user_id,
            token_hash=token_hash,
            label=label,
        )
        return raw_token, record.id

    @staticmethod
    def hash_cli_token(raw_token: str, secret: str) -> str:
        return hashlib.sha256(f"{secret}:{raw_token}".encode("utf-8")).hexdigest()

    @staticmethod
    def _identity_from_user(user: Any) -> WorkOSIdentity:
        if isinstance(user, dict):
            first_name = str(user.get("first_name", "") or "")
            last_name = str(user.get("last_name", "") or "")
            workos_user_id = str(user.get("id"))
            email = str(user.get("email", "")).strip().lower()
        else:
            first_name = getattr(user, "first_name", "") or ""
            last_name = getattr(user, "last_name", "") or ""
            workos_user_id = str(getattr(user, "id"))
            email = str(getattr(user, "email")).strip().lower()
        display_name = " ".join(part for part in [first_name, last_name] if part).strip()
        return WorkOSIdentity(
            workos_user_id=workos_user_id,
            email=email,
            display_name=display_name or None,
        )


def resolve_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return None
    return authorization.removeprefix("Bearer ").strip() or None


def require_approved_user(user: AuthUser | None) -> AuthUser:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if user.status == UserStatus.PENDING:
        raise HTTPException(status_code=403, detail="Approval required")
    if user.status == UserStatus.DISABLED:
        raise HTTPException(status_code=403, detail="Account disabled")
    return user


def require_admin_user(user: AuthUser | None) -> AuthUser:
    approved = require_approved_user(user)
    if not approved.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return approved


def _normalize_cookie_password(secret: str | None) -> str | None:
    if not secret:
        return None
    try:
        Fernet(secret.encode("utf-8"))
        return secret
    except Exception:
        digest = hashlib.sha256(secret.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8")


def _serialize_workos_value(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()

    result: dict[str, Any] = {}
    for field in ("id", "email", "first_name", "last_name"):
        field_value = getattr(value, field, None)
        if field_value is not None:
            result[field] = field_value
    return result or None

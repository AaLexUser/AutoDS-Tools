from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import os
import secrets
import shutil
import subprocess
import threading
import zipfile
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

import pygrad as pg
import yaml
from fastapi import (
    FastAPI,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from langchain_core.messages import (
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

from autods.agents.autods import AutoDSAgent
from autods.auth import AuthUser, UserStatus
from autods.runtime.runner import AgentRunner
from autods.sessions import (
    SessionMetadata,
    SessionNotFoundError,
    SessionOwnershipError,
    SessionService,
    SessionStatus,
    SessionStorage,
    SessionStorageError,
    TranscriptMessage,
    validate_principal_id,
)
from autods.utils.config import load_config

from .auth import (
    WORKOS_SESSION_COOKIE_NAME,
    AuthSettings,
    WorkOSAuthManager,
    require_admin_user,
    require_approved_user,
    resolve_bearer_token,
)
from .loggers import Tracer

logger = logging.getLogger(__name__)

COOKIE_PRINCIPAL_NAME = "autods_pid"
HEADER_PRINCIPAL_NAME = "X-AutoDS-Principal"
ARTIFACT_TREE_MAX_DEPTH = int(os.environ.get("ARTIFACT_TREE_MAX_DEPTH", "5"))
ARTIFACT_TREE_MAX_ITEMS = int(os.environ.get("ARTIFACT_TREE_MAX_ITEMS", "10000"))
ALLOWED_UPLOAD_EXTENSIONS = {
    ".csv",
    ".tsv",
    ".parquet",
    ".json",
    ".jsonl",
    ".md",
    ".txt",
    ".rst",
    ".yaml",
    ".yml",
    ".toml",
    ".py",
    ".ipynb",
}


class BootstrapResponse(BaseModel):
    principal_id: str


class AuthUserResponse(BaseModel):
    id: str
    email: str
    display_name: str | None = None
    status: str
    is_admin: bool


class AuthStateResponse(BaseModel):
    mode: str
    authenticated: bool
    user: AuthUserResponse | None = None


class CliTokenCreateRequest(BaseModel):
    label: str | None = None


class CliTokenCreateResponse(BaseModel):
    id: str
    token: str
    label: str | None = None


class CliTokenResponse(BaseModel):
    id: str
    label: str | None = None
    created_at: datetime
    last_used_at: datetime | None = None


class SessionResponse(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    status: str
    folder_size: int = 0


class TranscriptResponse(BaseModel):
    session_id: str
    status: str
    messages: list[dict[str, Any]]


class RunRequest(BaseModel):
    message: str
    options: dict[str, Any] | None = None


class RunResponse(BaseModel):
    session_id: str
    status: str


class AddDatasetRequest(BaseModel):
    url: str


class InstallLibrariesRequest(BaseModel):
    libraries: list[str]


class SessionRuntime:
    def start_run(
        self,
        session: SessionMetadata,
        prompt: str,
        run_options: dict[str, Any] | None = None,
    ) -> None:
        del run_options
        raise NotImplementedError

    def cancel_run(self, session: SessionMetadata) -> bool:
        return False

    def wait_for_completion(self, session_id: str, timeout: float) -> None:
        return None


class RunnerProtocol(Protocol):
    async def astream(
        self,
        prompt: str,
        *,
        callbacks: list[Any] | None = None,
        debug: bool = False,
    ) -> Any: ...


class WebSocketManager:
    def __init__(self) -> None:
        self.active_connections: dict[str, set[WebSocket]] = {}
        self._deleting_sessions: set[str] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        async with self._lock:
            if session_id in self._deleting_sessions:
                await websocket.accept()
                await websocket.close(code=1008, reason="Session is being deleted")
                return
        await websocket.accept()
        async with self._lock:
            if session_id in self._deleting_sessions:
                await websocket.close(code=1008, reason="Session is being deleted")
                return
            self.active_connections.setdefault(session_id, set()).add(websocket)

    async def disconnect(
        self, session_id: str, websocket: WebSocket | None = None
    ) -> None:
        async with self._lock:
            connections = self.active_connections.get(session_id)
            if not connections:
                return
            if websocket is None:
                to_close = list(connections)
                self.active_connections.pop(session_id, None)
            else:
                connections.discard(websocket)
                to_close = [websocket]
                if not connections:
                    self.active_connections.pop(session_id, None)
        for item in to_close:
            try:
                await item.close()
            except RuntimeError:
                pass

    async def send_payload(self, session_id: str, payload: dict[str, Any]) -> None:
        message = json.dumps(payload)
        async with self._lock:
            connections = list(self.active_connections.get(session_id, ()))
        failed: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_text(message)
            except Exception:
                failed.append(websocket)
        for websocket in failed:
            await self.disconnect(session_id, websocket)

    async def mark_session_deleting(self, session_id: str) -> None:
        async with self._lock:
            self._deleting_sessions.add(session_id)

    async def clear_session_deleting(self, session_id: str) -> None:
        async with self._lock:
            self._deleting_sessions.discard(session_id)


class HostedAgentRuntime(SessionRuntime):
    def __init__(
        self,
        storage: SessionStorage,
        manager: WebSocketManager,
        agent_options: dict[str, Any],
        runner_factory: Callable[[SessionMetadata], RunnerProtocol] | None = None,
    ) -> None:
        self.storage = storage
        self.manager = manager
        self.agent_options = agent_options
        self.runner_factory = runner_factory
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}
        self._cancel_events: dict[str, threading.Event] = {}

    def _build_runner(
        self,
        session: SessionMetadata,
        run_options: dict[str, Any] | None = None,
    ) -> RunnerProtocol:
        if self.runner_factory is not None:
            return self.runner_factory(session)
        merged_opts = dict(self.agent_options)
        if run_options:
            merged_opts.update({key: value for key, value in run_options.items()})
        service = SessionService(session.principal_id, storage=self.storage)
        workspace = Path(
            merged_opts.get("project_path") or service.workspace_path(session.id)
        )
        merged_opts["project_path"] = str(workspace.resolve())
        app_config = load_config(
            provider=merged_opts.get("provider"),
            model=merged_opts.get("model"),
            model_base_url=merged_opts.get("model_base_url"),
            api_key=merged_opts.get("api_key"),
            max_steps=merged_opts.get("max_steps"),
            config_file=merged_opts.get("config_file"),
        )
        agent = AutoDSAgent(
            app_config=app_config,
            project_path=merged_opts.get("project_path"),
        )
        return AgentRunner(
            agent=agent,
            project_path=merged_opts.get("project_path"),
            recursion_limit=merged_opts.get("max_steps") or 200,
            session=session,
        )

    def start_run(
        self,
        session: SessionMetadata,
        prompt: str,
        run_options: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            existing = self._threads.get(session.id)
            if existing and existing.is_alive():
                raise RuntimeError("Session already has a running task")
            cancel_event = threading.Event()
            self._cancel_events[session.id] = cancel_event
        main_loop = asyncio.get_running_loop()
        thread = threading.Thread(
            target=self._run_session,
            args=(session, prompt, main_loop, cancel_event, run_options),
            daemon=True,
        )
        with self._lock:
            self._threads[session.id] = thread
        thread.start()

    def cancel_run(self, session: SessionMetadata) -> bool:
        with self._lock:
            cancel_event = self._cancel_events.get(session.id)
        if cancel_event is None:
            return False
        cancel_event.set()
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
        main_loop: asyncio.AbstractEventLoop,
        cancel_event: threading.Event,
        run_options: dict[str, Any] | None = None,
    ) -> None:
        service = SessionService(session.principal_id, storage=self.storage)
        local_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(local_loop)
        current_message_id: str | None = None
        current_assistant_chunks: list[str] = []

        def _broadcast(payload: dict[str, Any]) -> None:
            if main_loop.is_closed():
                return
            try:
                main_loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(
                        self.manager.send_payload(session.id, payload)
                    )
                )
            except RuntimeError:
                logger.debug("Skipping websocket broadcast for closed event loop")

        def _finalize_assistant() -> None:
            nonlocal current_message_id, current_assistant_chunks
            if not current_assistant_chunks:
                return
            content = "".join(current_assistant_chunks)
            service.upsert_transcript_message(
                session.id,
                TranscriptMessage(
                    role="assistant",
                    content=content,
                    message_id=current_message_id,
                    is_streaming=False,
                ),
            )
            current_message_id = None
            current_assistant_chunks = []

        def _set_session_status(status: SessionStatus) -> bool:
            try:
                service.set_status(session.id, status)
                return True
            except SessionNotFoundError:
                logger.debug(
                    "Skipping status update for deleted session %s",
                    session.id,
                )
                return False

        try:
            runner = self._build_runner(session, run_options=run_options)
            trace_file = service.trace_path(session.id) / "tracing.yaml"
            tracer = Tracer(file_path=trace_file, reset=True)

            async def ui_callback(mode: str, chunk: Any) -> None:
                nonlocal current_message_id, current_assistant_chunks
                if cancel_event.is_set():
                    raise asyncio.CancelledError("Run cancelled")
                if mode != "messages":
                    return
                message = chunk[0] if isinstance(chunk, tuple) else chunk
                timestamp = datetime.now(UTC).isoformat()
                if isinstance(message, AIMessageChunk):
                    token = str(message.content or "")
                    if not token:
                        return
                    incoming_id = (
                        getattr(message, "id", None)
                        or current_message_id
                        or f"msg-{datetime.now(UTC).timestamp()}"
                    )
                    if current_message_id and incoming_id != current_message_id:
                        _finalize_assistant()
                    current_message_id = incoming_id
                    current_assistant_chunks.append(token)
                    service.upsert_transcript_message(
                        session.id,
                        TranscriptMessage(
                            role="assistant",
                            content="".join(current_assistant_chunks),
                            message_id=current_message_id,
                            timestamp=datetime.now(UTC),
                            is_streaming=True,
                        ),
                    )
                    _broadcast(
                        {
                            "type": "token",
                            "data": token,
                            "message_id": current_message_id,
                            "timestamp": timestamp,
                        }
                    )
                    return

                if isinstance(message, HumanMessage):
                    transcript_message = _human_transcript_message(
                        message,
                        user_prompt=prompt,
                    )
                else:
                    transcript_message = _environment_transcript_message(message)
                if transcript_message is None:
                    return
                _finalize_assistant()
                service.append_transcript_message(session.id, transcript_message)
                _broadcast(
                    {
                        "type": "environment",
                        "data": transcript_message.content,
                        "timestamp": transcript_message.timestamp.isoformat(),
                        "truncated": transcript_message.is_truncated,
                    }
                )

            async def _execute() -> None:
                try:
                    _broadcast(
                        {
                            "type": "status",
                            "data": "running",
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    )
                    await runner.astream(
                        prompt,
                        callbacks=[tracer.tracing_callback, ui_callback],
                        debug=True,
                    )
                    _finalize_assistant()
                    _set_session_status(SessionStatus.IDLE)
                    _broadcast(
                        {
                            "type": "status",
                            "data": "completed",
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    )
                except asyncio.CancelledError:
                    _finalize_assistant()
                    _set_session_status(SessionStatus.IDLE)
                    _broadcast(
                        {
                            "type": "status",
                            "data": "cancelled",
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    )
                except Exception as exc:
                    logger.exception("Run failed for session %s", session.id)
                    _finalize_assistant()
                    _set_session_status(SessionStatus.ERROR)
                    _broadcast(
                        {
                            "type": "status",
                            "data": f"Error: {exc}",
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    )
                finally:
                    try:
                        workspace = service.workspace_path(session.id, create=False)
                        service.update_folder_size(session.id, get_folder_size(workspace))
                    except SessionNotFoundError:
                        logger.debug(
                            "Skipping workspace metadata sync for deleted session %s",
                            session.id,
                        )
                    except Exception:
                        logger.exception(
                            "Failed to finalize workspace metadata for session %s",
                            session.id,
                        )

            local_loop.run_until_complete(_execute())
        except Exception as exc:
            logger.exception("Failed to initialize run for session %s", session.id)
            _set_session_status(SessionStatus.ERROR)
            _broadcast(
                {
                    "type": "status",
                    "data": f"Error: {exc}",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        finally:
            with self._lock:
                self._cancel_events.pop(session.id, None)
                self._threads.pop(session.id, None)
            local_loop.close()


def get_folder_size(path: Path) -> int:
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


def generate_principal_id() -> str:
    return secrets.token_urlsafe(24)


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


def _environment_transcript_message(
    message: BaseMessage,
) -> TranscriptMessage | None:
    is_tool_message = isinstance(message, ToolMessage)
    is_tool_role = getattr(message, "role", None) == "tool"
    if not is_tool_message and not is_tool_role:
        return None

    preview = _message_content_to_text(message.content)
    if not preview:
        return None

    truncated = len(preview) > 500
    return TranscriptMessage(
        role="environment",
        content=preview,
        is_truncated=truncated,
    )


def _human_transcript_message(
    message: HumanMessage,
    *,
    user_prompt: str,
) -> TranscriptMessage | None:
    if getattr(message, "role", None) == "tool":
        return _environment_transcript_message(message)

    content = _message_content_to_text(message.content)
    if not content:
        return None
    if content.strip() == user_prompt.strip():
        return None

    return TranscriptMessage(
        role="assistant",
        content=content,
        message_id=getattr(message, "id", None),
    )


def _build_transcript_response(
    session_id: str,
    status: SessionStatus,
    messages: list[TranscriptMessage],
) -> TranscriptResponse:
    return TranscriptResponse(
        session_id=session_id,
        status=status,
        messages=[
            {
                "id": message.message_id or f"{message.role}-{index}",
                "role": message.role,
                "content": message.content,
                "timestamp": message.timestamp.isoformat(),
                "isStreaming": message.is_streaming,
                "isTruncated": message.is_truncated,
            }
            for index, message in enumerate(messages, start=1)
        ],
    )


def create_app(
    agent_options: Optional[dict[str, Any]] = None,
    runtime: SessionRuntime | None = None,
    workos_client_factory: Callable[[], Any] | None = None,
) -> FastAPI:
    storage = SessionStorage()
    auth_settings = AuthSettings.from_env()
    auth_manager = WorkOSAuthManager(
        storage=storage,
        settings=auth_settings,
        workos_client_factory=workos_client_factory,
    )
    manager = WebSocketManager()
    default_agent_options = agent_options or {}
    runtime = runtime or HostedAgentRuntime(
        storage=storage,
        manager=manager,
        agent_options=default_agent_options,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield

    app = FastAPI(
        title="AutoDS API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _principal_from_request(request: Request) -> str | None:
        return request.headers.get(HEADER_PRINCIPAL_NAME) or request.cookies.get(
            COOKIE_PRINCIPAL_NAME
        )

    def _principal_from_websocket(websocket: WebSocket) -> str | None:
        return websocket.headers.get(HEADER_PRINCIPAL_NAME) or websocket.cookies.get(
            COOKIE_PRINCIPAL_NAME
        )

    def _require_principal(request: Request) -> str:
        if auth_settings.enabled:
            cli_user = auth_manager.resolve_cli_user(resolve_bearer_token(request))
            browser_user = cli_user or auth_manager.resolve_browser_user(request)
            return require_approved_user(browser_user).id
        principal_id = _principal_from_request(request)
        if principal_id:
            try:
                return validate_principal_id(principal_id)
            except SessionStorageError as exc:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid principal identity",
                ) from exc
        raise HTTPException(status_code=401, detail="Missing principal identity")

    def _session_service(principal_id: str) -> SessionService:
        return SessionService(principal_id=principal_id, storage=storage)

    def _auth_user_response(user: AuthUser) -> AuthUserResponse:
        return AuthUserResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            status=user.status,
            is_admin=user.is_admin,
        )

    def _get_owned_session(principal_id: str, session_id: str) -> SessionMetadata:
        service = _session_service(principal_id)
        try:
            return service.get_session(session_id)
        except SessionOwnershipError as exc:
            raise HTTPException(status_code=403, detail="Forbidden") from exc
        except SessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc

    def _set_auth_user_status(
        user_id: str,
        *,
        status: UserStatus,
        approved_by: str | None = None,
    ) -> AuthUser:
        try:
            return storage.set_auth_user_status(
                user_id,
                status=status,
                approved_by=approved_by,
            )
        except SessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail="User not found") from exc

    def _workspace_for(session: SessionMetadata, *, create: bool = True) -> Path:
        service = _session_service(session.principal_id)
        return service.workspace_path(session.id, create=create)

    def _session_response(session: SessionMetadata) -> SessionResponse:
        return SessionResponse(
            id=session.id,
            created_at=session.created_at,
            updated_at=session.updated_at,
            status=session.status,
            folder_size=session.folder_size,
        )

    @app.post("/api/bootstrap", response_model=BootstrapResponse)
    async def bootstrap(request: Request, response: Response):
        if auth_settings.enabled:
            raise HTTPException(status_code=404, detail="Bootstrap disabled")
        principal_id = _principal_from_request(request)
        if principal_id is not None:
            try:
                principal_id = validate_principal_id(principal_id)
            except SessionStorageError:
                principal_id = generate_principal_id()
        else:
            principal_id = generate_principal_id()
        response.set_cookie(
            key=COOKIE_PRINCIPAL_NAME,
            value=principal_id,
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 365,
        )
        return BootstrapResponse(principal_id=principal_id)

    @app.get("/api/auth/me", response_model=AuthStateResponse)
    async def auth_me(request: Request):
        if not auth_settings.enabled:
            return AuthStateResponse(mode=auth_settings.mode, authenticated=False)
        cli_user = auth_manager.resolve_cli_user(resolve_bearer_token(request))
        browser_user = cli_user or auth_manager.resolve_browser_user(request)
        if browser_user is None:
            return AuthStateResponse(mode=auth_settings.mode, authenticated=False)
        return AuthStateResponse(
            mode=auth_settings.mode,
            authenticated=True,
            user=_auth_user_response(browser_user),
        )

    @app.get("/api/auth/login")
    async def auth_login():
        return RedirectResponse(auth_manager.build_login_url(), status_code=307)

    @app.get("/api/auth/callback")
    async def auth_callback(code: str | None = None):
        user, sealed_session = auth_manager.exchange_code(code)
        redirect_response = RedirectResponse(auth_settings.frontend_root_url, status_code=307)
        redirect_response.set_cookie(
            key=WORKOS_SESSION_COOKIE_NAME,
            value=sealed_session,
            httponly=True,
            samesite="lax",
            secure=auth_settings.auth_cookie_secure,
            max_age=60 * 60 * 24 * 30,
        )
        return redirect_response

    @app.post("/api/auth/logout")
    async def auth_logout(request: Request):
        if not auth_settings.enabled:
            return {"status": "logged_out"}
        logout_url = auth_manager.logout_url(request.cookies.get(WORKOS_SESSION_COOKIE_NAME))
        response = RedirectResponse(logout_url, status_code=307)
        response.delete_cookie(WORKOS_SESSION_COOKIE_NAME)
        return response

    @app.get("/api/admin/users", response_model=list[AuthUserResponse])
    async def list_auth_users(request: Request):
        if not auth_settings.enabled:
            raise HTTPException(status_code=404, detail="Auth mode disabled")
        user = auth_manager.resolve_cli_user(resolve_bearer_token(request)) or auth_manager.resolve_browser_user(request)
        require_admin_user(user)
        return [_auth_user_response(item) for item in storage.list_auth_users()]

    @app.post("/api/admin/users/{user_id}/approve", response_model=AuthUserResponse)
    async def approve_auth_user(request: Request, user_id: str):
        if not auth_settings.enabled:
            raise HTTPException(status_code=404, detail="Auth mode disabled")
        admin = require_admin_user(
            auth_manager.resolve_cli_user(resolve_bearer_token(request))
            or auth_manager.resolve_browser_user(request)
        )
        user = _set_auth_user_status(
            user_id,
            status=UserStatus.APPROVED,
            approved_by=admin.id,
        )
        storage.append_audit_log(
            action="user.approved",
            actor_user_id=admin.id,
            target_user_id=user.id,
        )
        return _auth_user_response(user)

    @app.post("/api/admin/users/{user_id}/disable", response_model=AuthUserResponse)
    async def disable_auth_user(request: Request, user_id: str):
        if not auth_settings.enabled:
            raise HTTPException(status_code=404, detail="Auth mode disabled")
        admin = require_admin_user(
            auth_manager.resolve_cli_user(resolve_bearer_token(request))
            or auth_manager.resolve_browser_user(request)
        )
        user = _set_auth_user_status(user_id, status=UserStatus.DISABLED)
        storage.append_audit_log(
            action="user.disabled",
            actor_user_id=admin.id,
            target_user_id=user.id,
        )
        return _auth_user_response(user)

    @app.get("/api/auth/cli/tokens", response_model=list[CliTokenResponse])
    async def list_cli_tokens(request: Request):
        if not auth_settings.enabled:
            raise HTTPException(status_code=404, detail="Auth mode disabled")
        user = require_approved_user(auth_manager.resolve_browser_user(request))
        return [
            CliTokenResponse(
                id=item.id,
                label=item.label,
                created_at=item.created_at,
                last_used_at=item.last_used_at,
            )
            for item in storage.list_cli_tokens(user.id)
        ]

    @app.post("/api/auth/cli/tokens", response_model=CliTokenCreateResponse)
    async def create_cli_token(request: Request, body: CliTokenCreateRequest):
        if not auth_settings.enabled:
            raise HTTPException(status_code=404, detail="Auth mode disabled")
        user = require_approved_user(auth_manager.resolve_browser_user(request))
        raw_token, token_id = auth_manager.create_cli_token(user.id, label=body.label)
        return CliTokenCreateResponse(id=token_id, token=raw_token, label=body.label)

    @app.delete("/api/auth/cli/tokens/{token_id}")
    async def revoke_cli_token(request: Request, token_id: str):
        if not auth_settings.enabled:
            raise HTTPException(status_code=404, detail="Auth mode disabled")
        user = require_approved_user(auth_manager.resolve_browser_user(request))
        storage.revoke_cli_token(user.id, token_id)
        return {"status": "revoked", "id": token_id}

    @app.post("/api/sessions", response_model=SessionResponse)
    async def create_session(request: Request):
        principal_id = _require_principal(request)
        service = _session_service(principal_id)
        return _session_response(service.create_session())

    @app.get("/api/sessions", response_model=list[SessionResponse])
    async def list_sessions(request: Request):
        principal_id = _require_principal(request)
        service = _session_service(principal_id)
        return [_session_response(session) for session in service.list_sessions()]

    @app.get("/api/sessions/{session_id}", response_model=SessionResponse)
    async def get_session(request: Request, session_id: str):
        principal_id = _require_principal(request)
        return _session_response(_get_owned_session(principal_id, session_id))

    @app.get("/api/sessions/{session_id}/transcript", response_model=TranscriptResponse)
    async def get_transcript(request: Request, session_id: str):
        principal_id = _require_principal(request)
        service = _session_service(principal_id)
        session = _get_owned_session(principal_id, session_id)
        messages = service.list_transcript_messages(session.id)
        return _build_transcript_response(session.id, session.status, messages)

    @app.post("/api/sessions/{session_id}/runs", response_model=RunResponse)
    async def run_session(request: Request, session_id: str, body: RunRequest):
        principal_id = _require_principal(request)
        service = _session_service(principal_id)
        session = _get_owned_session(principal_id, session_id)
        if session.status in {SessionStatus.RUNNING, SessionStatus.CANCELLING}:
            raise HTTPException(status_code=409, detail="Session is already running")

        service.append_transcript_message(
            session.id,
            TranscriptMessage(role="user", content=body.message),
        )
        service.set_status(session.id, SessionStatus.RUNNING)
        session = service.get_session(session.id)
        try:
            runtime.start_run(session, body.message, run_options=body.options)
        except RuntimeError as exc:
            refreshed = service.get_session(session.id)
            if refreshed.status == SessionStatus.RUNNING:
                service.set_status(session.id, SessionStatus.ERROR)
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return RunResponse(session_id=session.id, status="started")

    @app.post("/api/sessions/{session_id}/cancel")
    async def cancel_session(request: Request, session_id: str):
        principal_id = _require_principal(request)
        service = _session_service(principal_id)
        session = _get_owned_session(principal_id, session_id)
        if runtime.cancel_run(session):
            service.set_status(session.id, SessionStatus.CANCELLING)
            await manager.send_payload(
                session.id,
                {
                    "type": "status",
                    "data": "cancelling",
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
            return {"status": "cancelling", "session_id": session.id}
        return {"status": "not_running", "session_id": session.id}

    @app.delete("/api/sessions/{session_id}")
    async def delete_session(request: Request, session_id: str):
        principal_id = _require_principal(request)
        service = _session_service(principal_id)
        session = _get_owned_session(principal_id, session_id)
        await manager.mark_session_deleting(session.id)
        try:
            runtime.cancel_run(session)
            await run_in_threadpool(runtime.wait_for_completion, session.id, 10.0)
            await manager.disconnect(session.id)
            session_root = service.session_path(session.id, create=False)
            if session_root.exists():
                await run_in_threadpool(shutil.rmtree, session_root)
            service.delete_session(session.id)
            return {"status": "deleted", "session_id": session.id}
        finally:
            await manager.clear_session_deleting(session.id)

    @app.post("/api/sessions/{session_id}/dataset")
    async def upload_dataset(
        request: Request, session_id: str, files: list[UploadFile] = File(...)
    ):
        principal_id = _require_principal(request)
        service = _session_service(principal_id)
        session = _get_owned_session(principal_id, session_id)
        workspace = _workspace_for(session)
        uploaded_paths: list[str] = []
        for item in files:
            filename = Path(item.filename or "").name
            ext = Path(filename).suffix.lower()
            if ext not in ALLOWED_UPLOAD_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"File type '{ext}' not allowed. Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}",
                )
            destination = workspace / filename
            destination.write_bytes(await item.read())
            uploaded_paths.append(filename)
        service.update_folder_size(session.id, get_folder_size(workspace))
        return {"paths": uploaded_paths}

    @app.post("/api/sessions/{session_id}/install")
    async def install_libraries(
        request: Request, session_id: str, body: InstallLibrariesRequest
    ):
        principal_id = _require_principal(request)
        service = _session_service(principal_id)
        session = _get_owned_session(principal_id, session_id)
        workspace = _workspace_for(session)

        if not body.libraries:
            return {"status": "no_libraries", "message": "No libraries specified"}

        venv_path = workspace / ".venv"
        pip_path = venv_path / "bin" / "pip"

        def _run_venv_create() -> None:
            subprocess.run(
                ["python3", "-m", "venv", str(venv_path)],
                check=True,
                capture_output=True,
            )

        def _run_pip_install() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [str(pip_path), "install", *body.libraries],
                capture_output=True,
                text=True,
                timeout=300,
            )

        try:
            if not venv_path.exists():
                await run_in_threadpool(_run_venv_create)
            result = await run_in_threadpool(_run_pip_install)
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(
                status_code=500, detail="Installation timed out after 5 minutes"
            ) from exc
        except Exception as exc:
            logger.exception("Failed to install libraries")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"pip install failed: {result.stderr}",
            )

        service.update_folder_size(session.id, get_folder_size(workspace))
        return {
            "status": "success",
            "installed": body.libraries,
            "output": result.stdout[-1000:] if result.stdout else "",
        }

    def _artifacts_root(session: SessionMetadata) -> Path:
        return _workspace_for(session, create=False)

    def _get_artifacts_sync(root: Path) -> dict[str, Any]:
        if not root.exists():
            return {"root": str(root), "tree": [], "files": [], "hash": ""}
        count = 0

        def scan_dir(path: Path, current_depth: int = 0) -> list[dict[str, Any]]:
            nonlocal count
            items: list[dict[str, Any]] = []
            if current_depth > ARTIFACT_TREE_MAX_DEPTH:
                return items
            try:
                entries = sorted(
                    path.iterdir(),
                    key=lambda item: (not item.is_dir(), item.name.lower()),
                )
            except PermissionError:
                return items
            for entry in entries:
                if count > ARTIFACT_TREE_MAX_ITEMS:
                    break
                if entry.name in {"__pycache__", ".venv"}:
                    continue
                rel_path = entry.relative_to(root).as_posix()
                if entry.is_dir():
                    items.append(
                        {
                            "type": "directory",
                            "name": entry.name,
                            "path": rel_path,
                            "children": scan_dir(entry, current_depth + 1),
                        }
                    )
                else:
                    count += 1
                    items.append(
                        {
                            "type": "file",
                            "name": entry.name,
                            "path": rel_path,
                            "size": entry.stat().st_size,
                        }
                    )
            return items

        tree = scan_dir(root)
        tree_hash = hashlib.md5(
            json.dumps(tree, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return {"root": str(root), "tree": tree, "files": [], "hash": tree_hash}

    def _create_zip_sync(root: Path) -> io.BytesIO:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in root.rglob("*"):
                if item.is_dir():
                    continue
                rel_path = item.relative_to(root)
                if ".venv" in rel_path.parts:
                    continue
                archive.write(item, rel_path.as_posix())
        buffer.seek(0)
        return buffer

    @app.get("/api/sessions/{session_id}/artifacts")
    async def get_artifacts(request: Request, session_id: str):
        principal_id = _require_principal(request)
        session = _get_owned_session(principal_id, session_id)
        return await run_in_threadpool(_get_artifacts_sync, _artifacts_root(session))

    @app.get("/api/sessions/{session_id}/file")
    async def get_file(request: Request, session_id: str, file_path: str):
        principal_id = _require_principal(request)
        session = _get_owned_session(principal_id, session_id)
        root = _artifacts_root(session).resolve()
        requested = (root / file_path).resolve()
        if not str(requested).startswith(str(root)):
            raise HTTPException(status_code=400, detail="Invalid file path")
        if not requested.exists():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(requested)

    @app.get("/api/sessions/{session_id}/artifacts/archive")
    async def download_artifact_archive(request: Request, session_id: str):
        principal_id = _require_principal(request)
        session = _get_owned_session(principal_id, session_id)
        root = _artifacts_root(session).resolve()
        if not root.exists():
            raise HTTPException(status_code=404, detail="No artifacts")
        buffer = await run_in_threadpool(_create_zip_sync, root)
        filename = f"{session_id}_artifacts.zip"
        return StreamingResponse(
            buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/datasets")
    async def list_datasets(request: Request):
        _require_principal(request)
        datasets = await pg.list()
        return [{"id": ds.name, "name": ds.name} for ds in (datasets or [])]

    @app.post("/api/datasets", status_code=201)
    async def add_dataset(request: Request, body: AddDatasetRequest):
        _require_principal(request)
        try:
            await pg.add(body.url)
            dataset = await pg.get_dataset(body.url)
            return {"id": dataset.name, "name": dataset.name}
        except Exception as exc:
            logger.exception("Failed to add dataset")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.delete("/api/datasets/{name}", status_code=204)
    async def delete_dataset(request: Request, name: str):
        _require_principal(request)
        try:
            await pg.delete(name)
        except Exception as exc:
            logger.exception("Failed to delete dataset")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/config")
    async def get_config(request: Request):
        _require_principal(request)
        from autods.constants import DEFAULT_CONFIG_PATH

        return {
            "yaml": DEFAULT_CONFIG_PATH.read_text()
            if DEFAULT_CONFIG_PATH.exists()
            else ""
        }

    @app.post("/api/config")
    async def update_config(request: Request, body: dict[str, str]):
        _require_principal(request)
        from autods.constants import DEFAULT_CONFIG_PATH

        try:
            yaml.safe_load(body.get("yaml", ""))
            DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            DEFAULT_CONFIG_PATH.write_text(body.get("yaml", ""))
            return {"message": "Success"}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.websocket("/api/ws/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str):
        if auth_settings.enabled:
            browser_user = auth_manager.authenticate_browser_user(
                websocket.cookies.get(WORKOS_SESSION_COOKIE_NAME)
            )
            try:
                principal_id = require_approved_user(browser_user).id
            except HTTPException as exc:
                await websocket.accept()
                await websocket.close(code=4401, reason=exc.detail)
                return
        else:
            raw_principal_id = _principal_from_websocket(websocket)
            if raw_principal_id is None:
                await websocket.accept()
                await websocket.close(code=4401, reason="Missing principal identity")
                return
            try:
                principal_id = validate_principal_id(raw_principal_id)
            except SessionStorageError:
                await websocket.accept()
                await websocket.close(code=4400, reason="Invalid principal identity")
                return
        try:
            _get_owned_session(principal_id, session_id)
        except HTTPException as exc:
            await websocket.accept()
            code = 4403 if exc.status_code == 403 else 4404
            await websocket.close(code=code, reason=exc.detail)
            return

        await manager.connect(websocket, session_id)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await manager.disconnect(session_id, websocket)
        except Exception:
            await manager.disconnect(session_id, websocket)

    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "timestamp": datetime.now(UTC).isoformat()}

    return app

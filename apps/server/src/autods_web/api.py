from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import os
import shutil
import subprocess
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, AsyncIterator

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
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

import pygrad as pg
from autods.autods import AutoDS, generate_principal_id
from autods.sessions import (
    SessionMetadata,
    SessionNotFoundError,
    SessionOwnershipError,
    SessionStatus,
    SessionStorageError,
    TranscriptMessage,
    validate_principal_id,
)

logger = logging.getLogger(__name__)

COOKIE_PRINCIPAL_NAME = "autods_pid"
HEADER_PRINCIPAL_NAME = "X-AutoDS-Principal"
ARTIFACT_TREE_MAX_DEPTH = int(os.environ.get("ARTIFACT_TREE_MAX_DEPTH", "5"))
ARTIFACT_TREE_MAX_ITEMS = int(os.environ.get("ARTIFACT_TREE_MAX_ITEMS", "10000"))
_PIP_INSTALL_TIMEOUT_SEC = max(1, int(os.environ.get("AUTODS_PIP_INSTALL_TIMEOUT_SEC", "3600")))
_PIP_INSTALL_STDERR_TAIL = int(os.environ.get("AUTODS_PIP_INSTALL_STDERR_TAIL", "12000"))
_UV_BIN = os.environ.get("AUTODS_UV_BIN", "uv")
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


def _venv_python_path(venv_path: Path) -> Path:
    return venv_path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _uv_venv_create_command(venv_path: Path) -> list[str]:
    return [_UV_BIN, "venv", "--seed", "--allow-existing", str(venv_path)]


def _uv_pip_install_command(venv_path: Path, libraries: list[str]) -> list[str]:
    return [_UV_BIN, "pip", "install", "--python", str(_venv_python_path(venv_path)), *libraries]


def _install_stream_event(event: dict[str, Any]) -> str:
    return json.dumps(event) + "\n"


async def _stream_command_output(command: list[str], phase: str) -> AsyncIterator[dict[str, Any]]:
    started_at = time.monotonic()
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert process.stdout is not None
    while True:
        if time.monotonic() - started_at > _PIP_INSTALL_TIMEOUT_SEC:
            process.kill()
            await process.wait()
            yield {"type": "error", "phase": phase, "message": "Installation timed out", "exit_code": None}
            yield {"type": "command_done", "phase": phase, "exit_code": 124}
            return
        try:
            raw_line = await asyncio.wait_for(process.stdout.readline(), timeout=0.2)
        except TimeoutError:
            if process.returncode is not None:
                break
            continue
        if not raw_line:
            if process.returncode is not None:
                break
            continue
        line = raw_line.decode(errors="replace").rstrip("\r\n")
        if line:
            yield {"type": "log", "phase": phase, "line": line}
    yield {"type": "command_done", "phase": phase, "exit_code": await process.wait()}


class BootstrapResponse(BaseModel):
    principal_id: str


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


class RunEvent(BaseModel):
    type: str
    session_id: str
    message_id: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    data: str | dict[str, Any] | None = None
    tool_started_at: str | None = None
    tool_completed_at: str | None = None
    tool_duration_ms: int | None = None
    timestamp: str


class RunRequest(BaseModel):
    message: str


class RunResponse(BaseModel):
    session_id: str
    status: str


class AddDatasetRequest(BaseModel):
    url: str


class InstallLibrariesRequest(BaseModel):
    libraries: list[str]


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

    async def disconnect(self, session_id: str, websocket: WebSocket | None = None) -> None:
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
                "toolCallId": message.tool_call_id,
                "toolName": message.tool_name,
                "toolArgs": message.tool_args,
                "toolResult": message.tool_result,
                "toolStatus": message.tool_status,
                "toolStartedAt": message.tool_started_at.isoformat() if message.tool_started_at else None,
                "toolCompletedAt": message.tool_completed_at.isoformat() if message.tool_completed_at else None,
                "toolDurationMs": message.tool_duration_ms,
            }
            for index, message in enumerate(messages, start=1)
        ],
    )


def create_app(
    autods: AutoDS | None = None,
) -> FastAPI:
    manager = WebSocketManager()
    autods = autods or AutoDS()
    app = FastAPI(
        title="AutoDS API",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _principal_from_request(request: Request) -> str | None:
        return request.headers.get(HEADER_PRINCIPAL_NAME) or request.cookies.get(COOKIE_PRINCIPAL_NAME)

    def _principal_from_websocket(websocket: WebSocket) -> str | None:
        return websocket.headers.get(HEADER_PRINCIPAL_NAME) or websocket.cookies.get(COOKIE_PRINCIPAL_NAME)

    def _require_principal(request: Request) -> str:
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

    def _get_owned_session(principal_id: str, session_id: str) -> SessionMetadata:
        try:
            return autods.get_session(principal_id, session_id)
        except SessionOwnershipError as exc:
            raise HTTPException(status_code=403, detail="Forbidden") from exc
        except SessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc

    def _workspace_for(session: SessionMetadata, *, create: bool = True) -> Path:
        return autods.workspace_path(session.principal_id, session.id, create=create)

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
            secure=False,
            max_age=60 * 60 * 24 * 365,
        )
        return BootstrapResponse(principal_id=principal_id)

    @app.post("/api/sessions", response_model=SessionResponse)
    async def create_session(request: Request):
        principal_id = _require_principal(request)
        return _session_response(autods.create_session(principal_id))

    @app.get("/api/sessions", response_model=list[SessionResponse])
    async def list_sessions(request: Request):
        principal_id = _require_principal(request)
        return [_session_response(session) for session in autods.list_sessions(principal_id)]

    @app.get("/api/sessions/{session_id}", response_model=SessionResponse)
    async def get_session(request: Request, session_id: str):
        principal_id = _require_principal(request)
        return _session_response(_get_owned_session(principal_id, session_id))

    @app.get("/api/sessions/{session_id}/transcript", response_model=TranscriptResponse)
    async def get_transcript(request: Request, session_id: str):
        principal_id = _require_principal(request)
        session = _get_owned_session(principal_id, session_id)
        messages = autods.list_transcript(principal_id, session.id)
        return _build_transcript_response(session.id, session.status, messages)

    @app.post("/api/sessions/{session_id}/runs", response_model=RunResponse)
    async def run_session(request: Request, session_id: str, body: RunRequest):
        principal_id = _require_principal(request)
        session = _get_owned_session(principal_id, session_id)
        if session.status in {SessionStatus.RUNNING, SessionStatus.CANCELLING}:
            raise HTTPException(status_code=409, detail="Session is already running")

        loop = asyncio.get_running_loop()

        def _broadcast_from_thread(payload: dict[str, Any]) -> None:
            if loop.is_closed():
                return
            try:
                loop.call_soon_threadsafe(lambda: asyncio.create_task(manager.send_payload(session.id, payload)))
            except RuntimeError:
                logger.debug("Skipping websocket broadcast for closed event loop")

        try:
            autods.start_run(
                principal_id,
                session.id,
                body.message,
                on_event=_broadcast_from_thread,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return RunResponse(session_id=session.id, status="started")

    @app.post("/api/sessions/{session_id}/cancel")
    async def cancel_session(request: Request, session_id: str):
        principal_id = _require_principal(request)
        session = _get_owned_session(principal_id, session_id)
        if autods.cancel_run(principal_id, session.id):
            await manager.send_payload(
                session.id,
                RunEvent(
                    type="run_cancelling",
                    session_id=session.id,
                    timestamp=datetime.now(UTC).isoformat(),
                ).model_dump(),
            )
            return {"status": "cancelling", "session_id": session.id}
        return {"status": "not_running", "session_id": session.id}

    @app.delete("/api/sessions/{session_id}")
    async def delete_session(request: Request, session_id: str):
        principal_id = _require_principal(request)
        session = _get_owned_session(principal_id, session_id)
        await manager.mark_session_deleting(session.id)
        try:
            autods.cancel_run(principal_id, session.id)
            await run_in_threadpool(autods.wait_for_completion, session.id, 10.0)
            await manager.disconnect(session.id)
            session_root = autods.session_path(principal_id, session.id, create=False)
            if session_root.exists():
                await run_in_threadpool(shutil.rmtree, session_root)
            autods.delete_session(principal_id, session.id)
            return {"status": "deleted", "session_id": session.id}
        finally:
            await manager.clear_session_deleting(session.id)

    @app.post("/api/sessions/{session_id}/dataset")
    async def upload_dataset(request: Request, session_id: str, files: list[UploadFile] = File(...)):
        principal_id = _require_principal(request)
        session = _get_owned_session(principal_id, session_id)
        workspace = _workspace_for(session)
        uploaded_paths: list[str] = []
        for item in files:
            filename = Path(item.filename or "").name
            ext = Path(filename).suffix.lower()
            if ext not in ALLOWED_UPLOAD_EXTENSIONS:
                raise HTTPException(status_code=400, detail=f"File type '{ext}' not allowed")
            (workspace / filename).write_bytes(await item.read())
            uploaded_paths.append(filename)
        autods.refresh_folder_size(principal_id, session.id)
        return {"paths": uploaded_paths}

    @app.post("/api/sessions/{session_id}/install")
    async def install_libraries(request: Request, session_id: str, body: InstallLibrariesRequest):
        principal_id = _require_principal(request)
        session = _get_owned_session(principal_id, session_id)
        workspace = _workspace_for(session)
        if not body.libraries:
            return {"status": "no_libraries", "message": "No libraries specified"}

        venv_path = workspace / ".venv"
        venv_python = _venv_python_path(venv_path)

        def _install() -> subprocess.CompletedProcess[str]:
            if not venv_python.exists():
                subprocess.run(_uv_venv_create_command(venv_path), check=True, capture_output=True)
            return subprocess.run(
                _uv_pip_install_command(venv_path, body.libraries),
                capture_output=True,
                text=True,
                timeout=_PIP_INSTALL_TIMEOUT_SEC,
            )

        try:
            result = await run_in_threadpool(_install)
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=504, detail="Installation timed out") from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        if result.returncode != 0:
            err = result.stderr or ""
            if len(err) > _PIP_INSTALL_STDERR_TAIL:
                err = "..." + err[-_PIP_INSTALL_STDERR_TAIL:]
            raise HTTPException(status_code=500, detail=f"uv pip install failed: {err}")

        autods.refresh_folder_size(principal_id, session.id)
        return {"status": "success", "installed": body.libraries, "output": result.stdout[-1000:]}

    @app.post("/api/sessions/{session_id}/install/stream")
    async def install_libraries_stream(request: Request, session_id: str, body: InstallLibrariesRequest):
        principal_id = _require_principal(request)
        session = _get_owned_session(principal_id, session_id)
        workspace = _workspace_for(session)

        async def _events() -> AsyncIterator[str]:
            started_at = time.monotonic()
            if not body.libraries:
                yield _install_stream_event({"type": "done", "status": "no_libraries"})
                return
            venv_path = workspace / ".venv"
            commands = []
            if not _venv_python_path(venv_path).exists():
                commands.append(("venv_create", _uv_venv_create_command(venv_path)))
            commands.append(("pip_install", _uv_pip_install_command(venv_path, body.libraries)))
            for phase, command in commands:
                yield _install_stream_event({"type": "command", "phase": phase, "command": command})
                exit_code = 1
                async for event in _stream_command_output(command, phase):
                    if event["type"] == "command_done":
                        exit_code = int(event["exit_code"])
                    else:
                        event["elapsed_ms"] = int((time.monotonic() - started_at) * 1000)
                        yield _install_stream_event(event)
                if exit_code != 0:
                    yield _install_stream_event({"type": "error", "phase": phase, "exit_code": exit_code})
                    return
            await run_in_threadpool(autods.refresh_folder_size, principal_id, session.id)
            yield _install_stream_event(
                {
                    "type": "done",
                    "status": "success",
                    "installed": body.libraries,
                    "elapsed_ms": int((time.monotonic() - started_at) * 1000),
                }
            )

        return StreamingResponse(_events(), media_type="application/x-ndjson")

    def _artifacts_root(session: SessionMetadata) -> Path:
        return _workspace_for(session, create=False)

    def _get_artifacts_sync(root: Path) -> dict[str, Any]:
        if not root.exists():
            return {"root": str(root), "tree": [], "files": [], "hash": ""}
        count = 0

        def scan_dir(path: Path, depth: int = 0) -> list[dict[str, Any]]:
            nonlocal count
            if depth > ARTIFACT_TREE_MAX_DEPTH or count > ARTIFACT_TREE_MAX_ITEMS:
                return []
            try:
                entries = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
            except PermissionError:
                return []
            items: list[dict[str, Any]] = []
            for entry in entries:
                if entry.name in {"__pycache__", ".venv"}:
                    continue
                rel_path = entry.relative_to(root).as_posix()
                if entry.is_dir():
                    items.append(
                        {
                            "type": "directory",
                            "name": entry.name,
                            "path": rel_path,
                            "children": scan_dir(entry, depth + 1),
                        }
                    )
                else:
                    count += 1
                    items.append({"type": "file", "name": entry.name, "path": rel_path, "size": entry.stat().st_size})
            return items

        tree = scan_dir(root)
        return {
            "root": str(root),
            "tree": tree,
            "files": [],
            "hash": hashlib.md5(json.dumps(tree, sort_keys=True).encode()).hexdigest(),
        }

    def _create_zip_sync(root: Path) -> io.BytesIO:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in root.rglob("*"):
                if item.is_file() and ".venv" not in item.relative_to(root).parts:
                    archive.write(item, item.relative_to(root).as_posix())
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
        return StreamingResponse(
            await run_in_threadpool(_create_zip_sync, root),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{session_id}_artifacts.zip"'},
        )

    @app.get("/api/datasets")
    async def list_datasets(request: Request):
        _require_principal(request)
        return [{"id": item.name, "name": item.name} for item in (await pg.list() or [])]

    @app.post("/api/datasets", status_code=201)
    async def add_dataset(request: Request, body: AddDatasetRequest):
        _require_principal(request)
        try:
            await pg.add(body.url)
            repo_id = pg.get_repository_id(body.url)
            dataset = await pg.get_dataset(repo_id)
            if dataset is None:
                raise HTTPException(status_code=500, detail="Dataset was not found after indexing")
            return {"id": dataset.name, "name": dataset.name}
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.delete("/api/datasets/{name}", status_code=204)
    async def delete_dataset(request: Request, name: str):
        _require_principal(request)
        await pg.delete(name)

    @app.websocket("/api/ws/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str):
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

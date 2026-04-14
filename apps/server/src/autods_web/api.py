import asyncio
import concurrent.futures
import hashlib
import io
import json
import logging
import os
import queue
import shutil
import threading
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pygrad as pg
import yaml
from fastapi import (
    FastAPI,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse
from langchain_core.messages import (
    AIMessageChunk,
    HumanMessage,
    HumanMessageChunk,
    ToolMessage,
)
from pydantic import BaseModel
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from autods.agents.autods import AutoDSAgent
from autods.runtime.runner import AgentRunner
from autods.sessions import SessionMetadata, SessionNotFoundError, SessionService
from autods.utils.config import load_config

from .loggers import Tracer

logger = logging.getLogger(__name__)
PROJECTS_ROOT = Path(os.environ.get("PROJECTS_ROOT", "/tmp/autods/projects"))
PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
ARTIFACT_TREE_MAX_DEPTH = int(os.environ.get("ARTIFACT_TREE_MAX_DEPTH", "5"))
ARTIFACT_TREE_MAX_ITEMS = int(os.environ.get("ARTIFACT_TREE_MAX_ITEMS", "10000"))
MAX_SESSION_HISTORY = int(os.environ.get("MAX_SESSION_HISTORY", "1000"))
SESSION_HISTORY_TRIM_TO = int(os.environ.get("SESSION_HISTORY_TRIM_TO", "500"))
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
SESSION_DELETION_MAX_WAIT = 10.0
SESSION_DELETION_POLL_INTERVAL = 0.1
SESSION_DELETION_WARNING_THRESHOLD = 2.0


class TaskRequest(BaseModel):
    task: str
    session_id: Optional[str] = None


class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = None


class SessionResponse(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    folder_size: int = 0


class TaskResponse(BaseModel):
    session_id: str
    status: str
    message: Optional[str] = None


class AddDatasetRequest(BaseModel):
    url: str


class InstallLibrariesRequest(BaseModel):
    libraries: List[str]


class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, set[WebSocket]] = {}
        self.aggregated_history: Dict[str, List[dict]] = {}
        self._current_message: Dict[str, dict] = {}
        self._deleting_sessions: set[str] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, session_id: str):
        async with self._lock:
            # Reject connections for sessions being deleted
            if session_id in self._deleting_sessions:
                await websocket.accept()
                await websocket.close(code=1008, reason="Session is being deleted")
                return
        await websocket.accept()
        async with self._lock:
            # Re-check after accepting in case deletion started during accept
            if session_id in self._deleting_sessions:
                await websocket.close(code=1008, reason="Session is being deleted")
                return
            self.active_connections.setdefault(session_id, set()).add(websocket)
            if (
                session_id in self.aggregated_history
                and self.aggregated_history[session_id]
            ):
                batch_msg = json.dumps(
                    {
                        "type": "history_batch",
                        "messages": self.aggregated_history[session_id],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
                await websocket.send_text(batch_msg)
        logger.info(
            "WebSocket connected for session %s (total %d)",
            session_id,
            len(self.active_connections.get(session_id, set())),
        )

    async def disconnect(self, session_id: str, websocket: Optional[WebSocket] = None):
        async with self._lock:
            connections = self.active_connections.get(session_id)
            if not connections:
                return
            if websocket:
                connections.discard(websocket)
            else:
                for ws in list(connections):
                    try:
                        await ws.close()
                    except RuntimeError:
                        pass
                connections.clear()
            if not connections:
                self.active_connections.pop(session_id, None)
                self._finalize_current_message(session_id)
        logger.info("WebSocket disconnected for session %s", session_id)

    def _finalize_current_message(self, session_id: str):
        """Finalize the current streaming message and add it to history.

        Note: Caller must hold self._lock to ensure thread safety.
        """
        if session_id not in self._current_message:
            return

        msg = self._current_message.pop(session_id)
        if not msg.get("content"):
            return

        msg["isStreaming"] = False

        if session_id not in self.aggregated_history:
            self.aggregated_history[session_id] = []

        self.aggregated_history[session_id].append(msg)

        # Keep history size manageable
        if len(self.aggregated_history[session_id]) > MAX_SESSION_HISTORY:
            original_len = len(self.aggregated_history[session_id])
            self.aggregated_history[session_id] = self.aggregated_history[session_id][
                -SESSION_HISTORY_TRIM_TO:
            ]
            logger.info(
                "Trimmed session %s history from %d to %d messages",
                session_id,
                original_len,
                SESSION_HISTORY_TRIM_TO,
            )

    async def send_message(self, session_id: str, message: str):
        async with self._lock:
            try:
                parsed = json.loads(message)
                msg_type = parsed.get("type")
                msg_data = parsed.get("data", "")
                msg_id = parsed.get("message_id")
                timestamp = parsed.get(
                    "timestamp", datetime.now(timezone.utc).isoformat()
                )

                if msg_type == "token":
                    current = self._current_message.get(session_id)
                    if current is None or (msg_id and current.get("id") != msg_id):
                        self._finalize_current_message(session_id)
                        self._current_message[session_id] = {
                            "id": msg_id
                            or f"msg-{datetime.now(timezone.utc).timestamp()}",
                            "role": "assistant",
                            "content": msg_data,
                            "timestamp": timestamp,
                            "isStreaming": True,
                        }
                    else:
                        current["content"] += msg_data

                elif msg_type in ("tool", "environment"):
                    self._finalize_current_message(session_id)
                    if session_id not in self.aggregated_history:
                        self.aggregated_history[session_id] = []
                    self.aggregated_history[session_id].append(
                        {
                            "id": f"{msg_type}-{datetime.now(timezone.utc).timestamp()}",
                            "role": "environment",
                            "content": msg_data,
                            "timestamp": timestamp,
                            "isStreaming": False,
                            "isTruncated": parsed.get("truncated", False),
                        }
                    )

                elif msg_type == "status":
                    completion_statuses = {"completed", "cancelled", "done"}
                    if msg_data in completion_statuses or msg_data.startswith("Error"):
                        self._finalize_current_message(session_id)

            except json.JSONDecodeError:
                pass

            connections = list(self.active_connections.get(session_id, ()))
            failed: list[WebSocket] = []
            for websocket in connections:
                try:
                    await websocket.send_text(message)
                except Exception as exc:
                    logger.error("WebSocket send failed (%s): %s", session_id, exc)
                    failed.append(websocket)

        for ws in failed:
            await self.disconnect(session_id, ws)

    async def add_user_message(self, session_id: str, content: str):
        async with self._lock:
            self._finalize_current_message(session_id)
            if session_id not in self.aggregated_history:
                self.aggregated_history[session_id] = []
            self.aggregated_history[session_id].append(
                {
                    "id": f"user-{datetime.now(timezone.utc).timestamp()}",
                    "role": "user",
                    "content": content,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "isStreaming": False,
                }
            )

    async def close_session(
        self, session_id: str, message: Optional[str] = None, code: int = 1000
    ):
        if message:
            await self.send_message(session_id, message)
        async with self._lock:
            self._finalize_current_message(session_id)
            connections = list(self.active_connections.pop(session_id, ()))
        for websocket in connections:
            await websocket.close(code=code)
        if connections:
            logger.info(
                "Closed %d WebSocket connection(s) for %s", len(connections), session_id
            )

    async def mark_session_deleting(self, session_id: str) -> None:
        """Mark a session as being deleted to prevent new connections."""
        async with self._lock:
            self._deleting_sessions.add(session_id)

    async def clear_session_data(self, session_id: str) -> None:
        """Clear all in-memory data for a session (history and current message)."""
        async with self._lock:
            self.aggregated_history.pop(session_id, None)
            self._current_message.pop(session_id, None)
            self._deleting_sessions.discard(session_id)


class CancellationRegistry:
    """Thread-safe registry for managing session cancellation."""

    def __init__(self):
        self._lock = threading.Lock()
        self._events: Dict[str, threading.Event] = {}
        self._runners: Dict[str, "AgentRunner"] = {}

    def register(self, session_id: str, runner: "AgentRunner") -> threading.Event:
        """Register a new session and return its cancellation event."""
        with self._lock:
            event = threading.Event()
            self._events[session_id] = event
            self._runners[session_id] = runner
            return event

    def cancel(self, session_id: str) -> bool:
        """Signal cancellation for a session. Returns True if session was found."""
        with self._lock:
            if session_id not in self._events:
                return False
            self._events[session_id].set()
            return True

    def is_running(self, session_id: str) -> bool:
        """Check if a session task is currently running."""
        with self._lock:
            return session_id in self._runners

    def unregister(self, session_id: str) -> None:
        with self._lock:
            self._events.pop(session_id, None)
            self._runners.pop(session_id, None)


cancellation_registry = CancellationRegistry()


def get_session_workspace(session_id: str, *, create: bool = True) -> Path:
    workspace = PROJECTS_ROOT / session_id
    if create:
        workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def get_folder_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat(follow_symlinks=False).st_size
            except (OSError, IOError) as exc:
                logger.warning("Failed to stat %s: %s", entry, exc)
    return total


def _artifacts_root(session_id: str) -> Path:
    return get_session_workspace(session_id, create=False)


def create_app(agent_options: Optional[dict[str, Any]] = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        async def _refresh_all_sizes():
            try:
                session_service = SessionService()
                sessions = session_service.list_sessions()
                for session in sessions:
                    try:
                        workspace = get_session_workspace(session.id, create=False)
                        size = await run_in_threadpool(get_folder_size, workspace)
                        session_service.update_folder_size(session.id, size)
                    except SessionNotFoundError:
                        logger.warning(
                            "Session %s was deleted during folder size refresh",
                            session.id,
                        )
                logger.info("Refreshed folder sizes for %d sessions", len(sessions))
            except Exception as e:
                logger.warning("Failed to refresh folder sizes on startup: %s", e)

        asyncio.create_task(_refresh_all_sizes())
        yield

    app = FastAPI(
        title="AutoDS API",
        version="0.1.0",
        lifespan=lifespan,
        middleware=[
            Middleware(
                CORSMiddleware,  # type: ignore[arg-type]  # Starlette typing limitation
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            ),
        ],
    )
    default_agent_options = agent_options or {}
    manager = WebSocketManager()

    def _ensure_session_exists(session_id: str) -> SessionMetadata:
        """Validate session exists and return it. Raises HTTPException if not found."""
        try:
            return SessionService().get_session(session_id)
        except SessionNotFoundError:
            raise HTTPException(status_code=404, detail="Session not found")

    async def _wait_for_session_termination(session_id: str) -> None:
        """Wait for agent task to complete before proceeding with deletion."""
        # Early exit if not running
        if not cancellation_registry.is_running(session_id):
            return

        elapsed = 0.0
        warned = False

        while elapsed < SESSION_DELETION_MAX_WAIT:
            if not cancellation_registry.is_running(session_id):
                return
            if elapsed > SESSION_DELETION_WARNING_THRESHOLD and not warned:
                logger.warning(
                    "Session %s taking longer than expected to terminate (%.1fs)",
                    session_id,
                    elapsed,
                )
                warned = True
            await asyncio.sleep(SESSION_DELETION_POLL_INTERVAL)
            elapsed += SESSION_DELETION_POLL_INTERVAL

        logger.error(
            "Session %s did not terminate after %.1fs, proceeding with deletion",
            session_id,
            SESSION_DELETION_MAX_WAIT,
        )

    def _start_agent_thread(
        task_request: TaskRequest,
        session: SessionMetadata,
        ws_manager: WebSocketManager,
        session_service: SessionService,
        main_loop: asyncio.AbstractEventLoop,
    ) -> None:
        """Start agent execution in background thread."""
        runner = build_runner(session)
        thread = threading.Thread(
            target=run_agent_sync_wrapper,
            kwargs={
                "task_request": task_request,
                "session": session,
                "runner": runner,
                "ws_manager": ws_manager,
                "session_service": session_service,
                "main_loop": main_loop,
            },
            daemon=True,
        )
        thread.start()

    def run_agent_sync_wrapper(
        task_request: TaskRequest,
        session: SessionMetadata,
        runner: AgentRunner,
        ws_manager: WebSocketManager,
        session_service: SessionService,
        main_loop: asyncio.AbstractEventLoop,
    ):
        local_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(local_loop)

        workspace = get_session_workspace(session.id)
        tracer = Tracer(file_path=workspace / "tracing.yaml", reset=True)

        cancel_event = cancellation_registry.register(session.id, runner)

        send_queue: queue.Queue[str | None] = queue.Queue()
        sender_task: concurrent.futures.Future[None] | None = None

        async def _sender_loop():
            """Consume messages from queue and send to WebSocket in order."""
            while True:
                try:
                    try:
                        msg = send_queue.get_nowait()
                    except queue.Empty:
                        await asyncio.sleep(0.01)
                        continue

                    if msg is None:
                        break
                    await ws_manager.send_message(session.id, msg)
                except Exception as exc:
                    logger.error("Sender loop error for %s: %s", session.id, exc)

        def _enqueue_message(
            msg_type: str,
            content: str,
            message_id: str | None = None,
            truncated: bool = False,
        ):
            """Thread-safe enqueue of a message (preserves order via FIFO queue)."""
            if not content:
                return
            payload: dict[str, Any] = {
                "type": msg_type,
                "data": str(content),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if message_id:
                payload["message_id"] = message_id
            if truncated:
                payload["truncated"] = True
            msg = json.dumps(payload)
            send_queue.put(msg)

        async def ui_callback(mode: str, chunk: Any):
            if cancel_event.is_set():
                raise asyncio.CancelledError("Agent execution cancelled by user")

            if mode == "messages":
                msg = chunk[0] if isinstance(chunk, tuple) else chunk

                if isinstance(msg, AIMessageChunk):
                    msg_id = getattr(msg, "id", None)
                    _enqueue_message("token", str(msg.content), message_id=msg_id)

                elif isinstance(msg, ToolMessage):
                    preview = (
                        str(msg.content)[:500] + "..."
                        if len(str(msg.content)) > 500
                        else str(msg.content)
                    )
                    _enqueue_message("tool", f"Tool Output: {preview}")

                elif isinstance(msg, (HumanMessage, HumanMessageChunk)):
                    full_content = str(msg.content)
                    is_truncated = len(full_content) > 500
                    _enqueue_message(
                        "environment", full_content, truncated=is_truncated
                    )

        async def _async_job():
            nonlocal sender_task
            sender_task = asyncio.run_coroutine_threadsafe(_sender_loop(), main_loop)

            had_error = False
            try:
                await runner.astream(
                    task_request.task,
                    callbacks=[tracer.tracing_callback, ui_callback],
                    debug=True,
                )

                session_service.upsert_session(session)
                _enqueue_message("status", "completed")
                logger.info("Task completed successfully for session %s", session.id)

            except asyncio.CancelledError:
                logger.info("Task cancelled by user for session %s", session.id)
                _enqueue_message("status", "cancelled")

            except Exception as exc:
                had_error = True
                logger.error(
                    "Error in thread job session %s: %s", session.id, exc, exc_info=True
                )
                _enqueue_message("status", f"Error: {str(exc)}")

            finally:
                cancellation_registry.unregister(session.id)

                try:
                    workspace = get_session_workspace(session.id, create=False)
                    size = get_folder_size(workspace)
                    session_service.update_folder_size(session.id, size)
                except Exception as exc:
                    logger.warning("Failed to update folder size: %s", exc)

                send_queue.put(None)
                if sender_task:
                    try:
                        sender_task.result(timeout=10.0)
                    except Exception as exc:
                        logger.warning("Sender task cleanup error: %s", exc)

                close_code = 1011 if had_error else 1000
                asyncio.run_coroutine_threadsafe(
                    ws_manager.close_session(session.id, code=close_code), main_loop
                )

        try:
            local_loop.run_until_complete(_async_job())
        finally:
            local_loop.close()

    def build_runner(session: SessionMetadata) -> AgentRunner:
        logger.info(f"Building agent runner for session: {session.id}")
        merged_opts = dict(default_agent_options)
        workspace = Path(
            merged_opts.get("project_path") or get_session_workspace(session.id)
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
        project_path = merged_opts.get("project_path")
        recursion_limit = merged_opts.get("max_steps") or 200
        agent = AutoDSAgent(app_config=app_config, project_path=project_path)
        return AgentRunner(
            agent=agent,
            project_path=project_path,
            recursion_limit=recursion_limit,
            session=session,
        )

    @app.post("/api/sessions", response_model=SessionResponse)
    async def create_session():
        session_service = SessionService()
        session = session_service.create_session()
        return SessionResponse(
            id=session.id,
            created_at=session.created_at,
            updated_at=session.updated_at,
            folder_size=session.folder_size,
        )

    @app.get("/api/sessions", response_model=List[SessionResponse])
    async def list_sessions():
        session_service = SessionService()
        return [
            SessionResponse(
                id=s.id,
                created_at=s.created_at,
                updated_at=s.updated_at,
                folder_size=s.folder_size,
            )
            for s in session_service.list_sessions()
        ]

    @app.get("/api/sessions/{session_id}", response_model=SessionResponse)
    async def get_session(session_id: str):
        session_service = SessionService()
        try:
            s = session_service.get_session(session_id)
            return SessionResponse(
                id=s.id,
                created_at=s.created_at,
                updated_at=s.updated_at,
                folder_size=s.folder_size,
            )
        except SessionNotFoundError:
            raise HTTPException(status_code=404)

    @app.post("/api/sessions/refresh-sizes")
    async def refresh_session_sizes():
        """Recalculate and cache folder sizes for all sessions."""
        session_service = SessionService()
        sessions = session_service.list_sessions()
        updated = 0
        for session in sessions:
            try:
                workspace = get_session_workspace(session.id, create=False)
                size = await run_in_threadpool(get_folder_size, workspace)
                session_service.update_folder_size(session.id, size)
                updated += 1
            except SessionNotFoundError:
                logger.warning(
                    "Session %s was deleted during folder size refresh", session.id
                )
        return {"status": "ok", "updated": updated}

    @app.delete("/api/sessions/{session_id}")
    async def delete_session(session_id: str):
        """Delete a session and all associated workspace files."""
        session_service = SessionService()
        _ensure_session_exists(session_id)

        await manager.mark_session_deleting(session_id)
        await manager.disconnect(session_id)
        cancellation_registry.cancel(session_id)
        await _wait_for_session_termination(session_id)

        workspace = get_session_workspace(session_id, create=False)
        if workspace.exists():
            await run_in_threadpool(shutil.rmtree, workspace)

        session_service.delete_session(session_id)

        await manager.clear_session_data(session_id)

        return {"status": "deleted", "session_id": session_id}

    @app.post("/api/execute", response_model=TaskResponse)
    async def execute_task(request: TaskRequest):
        session_service = SessionService()
        if request.session_id:
            try:
                session = session_service.get_session(request.session_id)
            except SessionNotFoundError:
                session = session_service.create_session()
        else:
            session = session_service.create_session()

        task_request = TaskRequest(task=request.task, session_id=session.id)
        main_loop = asyncio.get_running_loop()
        _start_agent_thread(task_request, session, manager, session_service, main_loop)

        return TaskResponse(
            session_id=session.id,
            status="started",
            message="Agent started in background thread",
        )

    @app.post("/api/chat")
    async def chat_message(request: ChatMessage):
        session_service = SessionService()
        if request.session_id:
            try:
                session = session_service.get_session(request.session_id)
            except SessionNotFoundError:
                raise HTTPException(status_code=404)
        else:
            session = session_service.create_session()

        await manager.add_user_message(session.id, request.message)

        task_request = TaskRequest(task=request.message, session_id=session.id)
        main_loop = asyncio.get_running_loop()
        _start_agent_thread(task_request, session, manager, session_service, main_loop)

        return {"status": "started", "session_id": session.id}

    @app.post("/api/session/{session_id}/cancel")
    async def cancel_session(session_id: str):
        """Cancel a running agent session."""
        _ensure_session_exists(session_id)

        if cancellation_registry.cancel(session_id):
            cancel_msg = json.dumps(
                {
                    "type": "status",
                    "data": "cancelling",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            await manager.send_message(session_id, cancel_msg)
            return {"status": "cancelling", "session_id": session_id}
        else:
            return {"status": "not_running", "session_id": session_id}

    @app.post("/api/session/{session_id}/dataset")
    async def upload_dataset(session_id: str, files: List[UploadFile] = File(...)):
        _ensure_session_exists(session_id)
        workspace = get_session_workspace(session_id)
        uploaded_paths = []

        for file in files:
            filename = Path(file.filename or "").name
            ext = Path(filename).suffix.lower()
            if ext not in ALLOWED_UPLOAD_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"File type '{ext}' not allowed. Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}",
                )

            dest = workspace / filename
            content = await file.read()
            dest.write_bytes(content)
            uploaded_paths.append(filename)
            logger.info("Dataset %s uploaded for session %s", filename, session_id)

        return {"paths": uploaded_paths}

    @app.get("/api/datasets")
    async def list_datasets():
        datasets = await pg.list()
        return [{"id": ds.name, "name": ds.name} for ds in (datasets or [])]

    @app.post("/api/datasets", status_code=201)
    async def add_dataset(request: AddDatasetRequest):
        try:
            await pg.add(request.url)
        except Exception as exc:
            logger.error("Failed to add dataset %s: %s", request.url, exc)
            raise HTTPException(status_code=500, detail=str(exc))
        ds = await pg.get_dataset(request.url)
        return {"id": ds.name, "name": ds.name}

    @app.delete("/api/datasets/{name}", status_code=204)
    async def delete_dataset(name: str):
        try:
            await pg.delete(name)
        except Exception as exc:
            logger.error("Failed to delete dataset %s: %s", name, exc)
            raise HTTPException(status_code=500, detail=str(exc))

    @app.websocket("/api/ws/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str):
        await manager.connect(websocket, session_id)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await manager.disconnect(session_id, websocket)
        except Exception:
            await manager.disconnect(session_id, websocket)

    @app.get("/api/session/{session_id}/history")
    async def get_session_history(session_id: str):
        session_service = SessionService()
        try:
            session = session_service.get_session(session_id)
            runner = build_runner(session)
            state = await runner.get_state()
            messages = state.values.get("messages") or [] if state else []
            return {
                "session_id": session.id,
                "messages": [
                    {"type": type(msg).__name__, "content": msg.content}
                    for msg in messages
                ],
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/config")
    async def get_config():
        from autods.constants import DEFAULT_CONFIG_PATH

        return {
            "yaml": DEFAULT_CONFIG_PATH.read_text()
            if DEFAULT_CONFIG_PATH.exists()
            else ""
        }

    @app.post("/api/config")
    async def update_config(request: Dict[str, str]):
        from autods.constants import DEFAULT_CONFIG_PATH

        try:
            yaml.safe_load(request.get("yaml", ""))
            if not DEFAULT_CONFIG_PATH.parent.exists():
                DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            DEFAULT_CONFIG_PATH.write_text(request.get("yaml", ""))
            return {"message": "Success"}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "timestamp": datetime.now().isoformat()}

    @app.post("/api/session/{session_id}/install")
    async def install_libraries(session_id: str, request: InstallLibrariesRequest):
        """Install Python libraries in the session's venv."""
        _ensure_session_exists(session_id)
        workspace = get_session_workspace(session_id)

        if not request.libraries:
            return {"status": "no_libraries", "message": "No libraries specified"}

        venv_path = workspace / ".venv"
        pip_path = venv_path / "bin" / "pip"

        import subprocess

        def _run_venv_create():
            subprocess.run(
                ["python3", "-m", "venv", str(venv_path)],
                check=True,
                capture_output=True,
            )

        def _run_pip_install():
            return subprocess.run(
                [str(pip_path), "install"] + request.libraries,
                capture_output=True,
                text=True,
                timeout=300,
            )

        try:
            if not venv_path.exists():
                await run_in_threadpool(_run_venv_create)
                logger.info("Created venv at %s", venv_path)

            result = await run_in_threadpool(_run_pip_install)

            if result.returncode != 0:
                raise HTTPException(
                    status_code=500,
                    detail=f"pip install failed: {result.stderr}",
                )

            return {
                "status": "success",
                "installed": request.libraries,
                "output": result.stdout[-1000:] if result.stdout else "",
            }
        except subprocess.TimeoutExpired:
            raise HTTPException(
                status_code=500, detail="Installation timed out after 5 minutes"
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to install libraries: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/session/{session_id}/artifacts/snapshot")
    async def refresh_snapshot(session_id: str):
        _ensure_session_exists(session_id)
        return {"status": "ok"}

    def _get_artifacts_sync(session_id: str):
        root = _artifacts_root(session_id)
        if not root.exists():
            return {"root": str(root), "tree": [], "files": [], "hash": ""}
        count = 0

        def scan_dir(path, current_depth=0):
            nonlocal count
            items = []
            if current_depth > ARTIFACT_TREE_MAX_DEPTH:
                return []
            try:
                entries = sorted(
                    path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())
                )
            except PermissionError:
                return []
            for entry in entries:
                if count > ARTIFACT_TREE_MAX_ITEMS:
                    break
                if entry.name == "__pycache__":
                    continue
                if entry.name == ".venv":
                    continue
                rel_path = entry.relative_to(root).as_posix()
                if entry.is_dir():
                    children = scan_dir(entry, current_depth + 1)
                    items.append(
                        {
                            "type": "directory",
                            "name": entry.name,
                            "path": rel_path,
                            "children": children,
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
        tree_str = json.dumps(tree, sort_keys=True, default=str)
        data_hash = hashlib.md5(tree_str.encode("utf-8")).hexdigest()
        return {"root": str(root), "tree": tree, "files": [], "hash": data_hash}

    def _create_zip_sync(root: Path) -> io.BytesIO:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for obj in root.rglob("*"):
                if obj.is_dir():
                    continue
                rel_path = obj.relative_to(root)
                if ".venv" in rel_path.parts:
                    continue
                try:
                    zf.write(obj, rel_path.as_posix())
                except Exception as e:
                    logger.warning(f"Could not zip file {obj}: {e}")
        buffer.seek(0)
        return buffer

    @app.get("/api/session/{session_id}/artifacts")
    async def get_artifacts(session_id: str):
        _ensure_session_exists(session_id)
        return await run_in_threadpool(_get_artifacts_sync, session_id)

    @app.get("/api/session/{session_id}/file")
    async def get_file(session_id: str, file_path: str):
        _ensure_session_exists(session_id)
        root = _artifacts_root(session_id).resolve()
        requested = (root / file_path).resolve()
        if not str(requested).startswith(str(root)):
            raise HTTPException(status_code=400)
        if not requested.exists():
            raise HTTPException(status_code=404)
        return FileResponse(requested)

    @app.get("/api/session/{session_id}/artifacts/archive")
    async def download_artifact_archive(session_id: str):
        _ensure_session_exists(session_id)
        root = _artifacts_root(session_id).resolve()
        if not root.exists():
            raise HTTPException(status_code=404, detail="No artifacts")
        buffer = await run_in_threadpool(_create_zip_sync, root)
        filename = f"{session_id}_artifacts.zip"
        return StreamingResponse(
            buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return app

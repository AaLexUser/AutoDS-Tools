from __future__ import annotations

import asyncio
import threading
import time
from base64 import urlsafe_b64encode
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk, HumanMessage
from starlette.websockets import WebSocketDisconnect
from workos.session import unseal_data

import autods_web.api as api_module
from autods.sessions import SessionService, TranscriptMessage
from autods_web.api import (
    COOKIE_PRINCIPAL_NAME,
    HEADER_PRINCIPAL_NAME,
    HostedAgentRuntime,
    SessionRuntime,
    SessionStorage,
    WebSocketManager,
    create_app,
)


class FakeRuntime(SessionRuntime):
    def __init__(self, storage_root: Path) -> None:
        self.storage_root = storage_root
        self.started_runs: list[tuple[str, str, str, dict[str, object] | None]] = []
        self.cancelled_sessions: list[str] = []

    def start_run(
        self,
        session,
        prompt: str,
        run_options: dict[str, object] | None = None,
    ) -> None:
        self.started_runs.append((session.principal_id, session.id, prompt, run_options))
        service = SessionService(
            principal_id=session.principal_id,
            root=self.storage_root,
        )
        service.append_transcript_message(
            session.id,
            TranscriptMessage(role="assistant", content=f"echo:{prompt}"),
        )
        service.set_status(session.id, "idle")

    def cancel_run(self, session) -> bool:
        self.cancelled_sessions.append(session.id)
        return True


class FakeWorkOSSession:
    def __init__(self, identity: dict[str, str] | None) -> None:
        self.identity = identity

    def authenticate(self):
        class Result:
            def __init__(self, identity: dict[str, str] | None) -> None:
                self.authenticated = identity is not None
                if identity is None:
                    self.user = None
                else:
                    self.user = type(
                        "User",
                        (),
                        {
                            "id": identity["workos_user_id"],
                            "email": identity["email"],
                            "first_name": identity.get("first_name", ""),
                            "last_name": identity.get("last_name", ""),
                        },
                    )()

        return Result(self.identity)

    def get_logout_url(self) -> str:
        return "http://localhost:3000/"


class FakeUserManagement:
    def __init__(self) -> None:
        self.codes: dict[str, tuple[str, dict[str, str]]] = {}
        self.sessions: dict[str, dict[str, str]] = {}

    def add_identity(
        self,
        *,
        code: str,
        sealed_session: str,
        workos_user_id: str,
        email: str,
        first_name: str = "Test",
        last_name: str = "User",
    ) -> None:
        identity = {
            "workos_user_id": workos_user_id,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
        }
        self.codes[code] = (sealed_session, identity)
        self.sessions[sealed_session] = identity

    def get_authorization_url(self, *, provider: str, redirect_uri: str) -> str:
        return f"{redirect_uri}?provider={provider}"

    def authenticate_with_code(self, *, code: str, **_: Any):
        sealed_session, identity = self.codes[code]

        class Response:
            def __init__(self, sealed_session: str, identity: dict[str, str]) -> None:
                self.access_token = f"access-token:{sealed_session}"
                self.refresh_token = f"refresh-token:{sealed_session}"
                self.impersonator = None
                self.user = type(
                    "User",
                    (),
                    {
                        "id": identity["workos_user_id"],
                        "email": identity["email"],
                        "first_name": identity.get("first_name", ""),
                        "last_name": identity.get("last_name", ""),
                    },
                )()

        return Response(sealed_session, identity)

    def load_sealed_session(self, *, session_data: str | None, cookie_password: str):
        identity = self.sessions.get(session_data or "")
        if identity is None and session_data:
            session = unseal_data(session_data, cookie_password)
            user = session.get("user", {})
            if user:
                identity = {
                    "workos_user_id": str(user["id"]),
                    "email": str(user["email"]),
                    "first_name": str(user.get("first_name", "")),
                    "last_name": str(user.get("last_name", "")),
                }
        return FakeWorkOSSession(identity)


class FakeWorkOSClient:
    def __init__(self) -> None:
        self.user_management = FakeUserManagement()


@pytest.fixture
def session_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "sessions"
    monkeypatch.setenv("AUTODS_SESSION_HOME", str(root))
    monkeypatch.setenv("AUTH_MODE", "disabled")
    return root


def _bootstrap(client: TestClient) -> str:
    response = client.post("/api/bootstrap")
    assert response.status_code == 200
    assert COOKIE_PRINCIPAL_NAME in client.cookies
    return response.json()["principal_id"]


def _create_client(session_root: Path) -> tuple[TestClient, FakeRuntime]:
    runtime = FakeRuntime(session_root)
    app = create_app(runtime=runtime)
    return TestClient(app), runtime


def _valid_cookie_secret(seed: str) -> str:
    return urlsafe_b64encode(sha256(seed.encode("utf-8")).digest()).decode("utf-8")


def _wait_for_transcript_message(
    client: TestClient,
    session_id: str,
    *,
    attempts: int = 20,
) -> dict[str, object]:
    for _ in range(attempts):
        response = client.get(f"/api/sessions/{session_id}/transcript")
        assert response.status_code == 200
        messages = response.json()["messages"]
        if len(messages) > 1:
            return response.json()
        time.sleep(0.01)
    pytest.fail("Timed out waiting for transcript message")


def test_bootstrap_sets_cookie_and_sessions_are_principal_scoped(
    session_root: Path,
) -> None:
    first_client, _ = _create_client(session_root)
    second_client, _ = _create_client(session_root)

    first_principal = _bootstrap(first_client)
    second_principal = _bootstrap(second_client)

    assert first_principal != second_principal

    first_session = first_client.post("/api/sessions")
    second_session = second_client.post("/api/sessions")

    assert first_session.status_code == 200
    assert second_session.status_code == 200

    first_list = first_client.get("/api/sessions")
    second_list = second_client.get("/api/sessions")

    assert first_list.status_code == 200
    assert second_list.status_code == 200
    assert [item["id"] for item in first_list.json()] == [first_session.json()["id"]]
    assert [item["id"] for item in second_list.json()] == [second_session.json()["id"]]


def test_foreign_session_access_returns_403(session_root: Path) -> None:
    owner_client, _ = _create_client(session_root)
    other_client, _ = _create_client(session_root)

    _bootstrap(owner_client)
    _bootstrap(other_client)

    session_id = owner_client.post("/api/sessions").json()["id"]

    for method, path in [
        ("get", f"/api/sessions/{session_id}"),
        ("get", f"/api/sessions/{session_id}/transcript"),
        ("post", f"/api/sessions/{session_id}/runs"),
        ("delete", f"/api/sessions/{session_id}"),
    ]:
        kwargs = {"json": {"message": "hi"}} if method == "post" else {}
        response = getattr(other_client, method)(path, **kwargs)
        assert response.status_code == 403


def test_invalid_session_does_not_get_recreated(session_root: Path) -> None:
    client, runtime = _create_client(session_root)
    _bootstrap(client)

    missing_id = "missing-session"

    missing_session = client.get(f"/api/sessions/{missing_id}")
    missing_run = client.post(
        f"/api/sessions/{missing_id}/runs",
        json={"message": "hello"},
    )

    assert missing_session.status_code == 404
    assert missing_run.status_code == 404
    assert runtime.started_runs == []
    assert client.get("/api/sessions").json() == []


def test_hosted_runtime_builds_runner_without_legacy_config_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = SessionStorage(root=tmp_path / "sessions")
    service = SessionService(principal_id="principal", storage=storage)
    session = service.create_session()
    manager = WebSocketManager()
    runtime = HostedAgentRuntime(
        storage=storage,
        manager=manager,
        agent_options={"project_path": str(tmp_path.resolve())},
    )
    captured: dict[str, object] = {}
    fake_llm_client = object()

    class FakeAgent:
        def __init__(self, project_path: str, *, llm_client: object) -> None:
            captured["project_path"] = project_path
            captured["llm_client"] = llm_client

    class FakeRunner:
        def __init__(self, agent, project_path, recursion_limit, session) -> None:
            captured["agent"] = agent
            captured["runner_project_path"] = project_path
            captured["recursion_limit"] = recursion_limit
            captured["session_id"] = session.id

    assert not hasattr(api_module, "load_config")
    monkeypatch.setattr(api_module, "AutoDSAgent", FakeAgent)
    monkeypatch.setattr(api_module, "AgentRunner", FakeRunner)
    monkeypatch.setattr(api_module, "build_llm_client", lambda _options: fake_llm_client)

    runner = runtime._build_runner(session)

    assert runner is not None
    assert captured["project_path"] == str(tmp_path.resolve())
    assert captured["llm_client"] is fake_llm_client
    assert captured["runner_project_path"] == str(tmp_path.resolve())
    assert captured["recursion_limit"] == 200
    assert captured["session_id"] == session.id


def test_invalid_principal_id_is_rejected_before_creating_session_paths(
    session_root: Path,
) -> None:
    client, _ = _create_client(session_root)

    response = client.post(
        "/api/sessions",
        headers={HEADER_PRINCIPAL_NAME: "../../escaped"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid principal identity"
    assert not (session_root.parent / "escaped").exists()


def test_add_dataset_looks_up_created_dataset_by_repository_id(
    session_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _create_client(session_root)
    _bootstrap(client)

    async def fake_add(url: str) -> None:
        assert url == "https://github.com/owner/repo"

    async def fake_get_dataset(dataset_name: str):
        assert dataset_name == "owner-repo"
        return SimpleNamespace(name="owner-repo")

    monkeypatch.setattr("autods_web.api.pg.add", fake_add)
    monkeypatch.setattr("autods_web.api.pg.get_dataset", fake_get_dataset)

    response = client.post(
        "/api/datasets",
        json={"url": "https://github.com/owner/repo"},
    )

    assert response.status_code == 201
    assert response.json() == {"id": "owner-repo", "name": "owner-repo"}


def test_add_dataset_returns_meaningful_error_when_indexed_dataset_is_missing(
    session_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _create_client(session_root)
    _bootstrap(client)

    async def fake_add(url: str) -> None:
        assert url == "https://github.com/owner/repo"

    async def fake_get_dataset(dataset_name: str):
        assert dataset_name == "owner-repo"
        return None

    monkeypatch.setattr("autods_web.api.pg.add", fake_add)
    monkeypatch.setattr("autods_web.api.pg.get_dataset", fake_get_dataset)

    response = client.post(
        "/api/datasets",
        json={"url": "https://github.com/owner/repo"},
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Dataset was not found after indexing"}


def test_delete_dataset_passes_repository_id_to_pygrad(session_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _create_client(session_root)
    _bootstrap(client)
    calls: list[str] = []

    async def fake_delete(value: str) -> None:
        calls.append(value)

    monkeypatch.setattr("autods_web.api.pg.delete", fake_delete)

    response = client.delete("/api/datasets/owner-repo")

    assert response.status_code == 204
    assert calls == ["owner-repo"]


def test_run_request_passes_options_to_runtime(session_root: Path) -> None:
    client, runtime = _create_client(session_root)
    principal_id = _bootstrap(client)
    session_id = client.post("/api/sessions").json()["id"]

    run_response = client.post(
        f"/api/sessions/{session_id}/runs",
        json={
            "message": "hello",
            "options": {
                "project_path": "/tmp/project",
                "model": "gpt-5",
                "max_steps": 42,
            },
        },
    )

    assert run_response.status_code == 200
    assert runtime.started_runs == [
        (
            principal_id,
            session_id,
            "hello",
            {
                "project_path": "/tmp/project",
                "model": "gpt-5",
                "max_steps": 42,
            },
        )
    ]


def test_transcript_persists_across_app_restart(session_root: Path) -> None:
    first_client, _ = _create_client(session_root)
    principal_id = _bootstrap(first_client)

    create_response = first_client.post("/api/sessions")
    session_id = create_response.json()["id"]

    run_response = first_client.post(
        f"/api/sessions/{session_id}/runs",
        json={"message": "hello"},
    )

    assert run_response.status_code == 200

    transcript = first_client.get(f"/api/sessions/{session_id}/transcript")
    assert transcript.status_code == 200
    assert transcript.json()["status"] == "idle"
    assert [item["role"] for item in transcript.json()["messages"]] == [
        "user",
        "assistant",
    ]

    second_client, _ = _create_client(session_root)
    second_client.cookies.set(COOKIE_PRINCIPAL_NAME, principal_id)

    reloaded = second_client.get(f"/api/sessions/{session_id}/transcript")
    assert reloaded.status_code == 200
    assert [item["content"] for item in reloaded.json()["messages"]] == [
        "hello",
        "echo:hello",
    ]


def test_websocket_rejects_foreign_session_owner(session_root: Path) -> None:
    owner_client, _ = _create_client(session_root)
    other_client, _ = _create_client(session_root)

    _bootstrap(owner_client)
    _bootstrap(other_client)

    session_id = owner_client.post("/api/sessions").json()["id"]

    with pytest.raises(WebSocketDisconnect):
        with other_client.websocket_connect(f"/api/ws/{session_id}") as websocket:
            websocket.receive_text()


class FakeHostedRunner:
    async def astream(self, prompt: str, *, callbacks=None, debug: bool = False) -> None:
        del prompt, debug
        if callbacks is None:
            return
        tool_message = HumanMessage(
            content=[
                {"type": "text", "text": ">>> [bash #1]\nalpha\nbeta"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ],
            role="tool",
        )
        for callback in callbacks:
            await callback("messages", tool_message)
            await callback(
                "messages",
                HumanMessage(content="I found the relevant files and will inspect them next."),
            )


def test_hosted_runtime_persists_tool_output_as_environment_messages(
    session_root: Path,
) -> None:
    storage = SessionStorage(root=session_root)
    runtime = HostedAgentRuntime(
        storage=storage,
        manager=WebSocketManager(),
        agent_options={},
        runner_factory=lambda _session: FakeHostedRunner(),
    )
    client = TestClient(create_app(runtime=runtime))

    _bootstrap(client)
    session_id = client.post("/api/sessions").json()["id"]

    run_response = client.post(
        f"/api/sessions/{session_id}/runs",
        json={"message": "hello"},
    )

    assert run_response.status_code == 200
    runtime.wait_for_completion(session_id, timeout=1.0)

    transcript = client.get(f"/api/sessions/{session_id}/transcript")
    assert transcript.status_code == 200
    roles = [item["role"] for item in transcript.json()["messages"]]
    assert roles == ["user", "environment", "assistant"]
    assert transcript.json()["messages"][1]["content"] == (
        ">>> [bash #1]\nalpha\nbeta\n[image output omitted: 1 image]"
    )
    assert transcript.json()["messages"][2]["content"] == ("I found the relevant files and will inspect them next.")


def test_environment_transcript_keeps_full_content_when_marked_truncated(
    session_root: Path,
) -> None:
    long_output = ">>> [python #1]\n" + ("0123456789" * 80)

    class FakeLongEnvironmentRunner:
        async def astream(
            self,
            prompt: str,
            *,
            callbacks=None,
            debug: bool = False,
        ) -> None:
            del prompt, debug
            if callbacks is None:
                return
            tool_message = HumanMessage(content=long_output, role="tool")
            for callback in callbacks:
                await callback("messages", tool_message)

    storage = SessionStorage(root=session_root)
    runtime = HostedAgentRuntime(
        storage=storage,
        manager=WebSocketManager(),
        agent_options={},
        runner_factory=lambda _session: FakeLongEnvironmentRunner(),
    )
    client = TestClient(create_app(runtime=runtime))

    _bootstrap(client)
    session_id = client.post("/api/sessions").json()["id"]

    run_response = client.post(
        f"/api/sessions/{session_id}/runs",
        json={"message": "hello"},
    )
    assert run_response.status_code == 200
    runtime.wait_for_completion(session_id, timeout=1.0)

    transcript = client.get(f"/api/sessions/{session_id}/transcript")
    assert transcript.status_code == 200
    environment_message = transcript.json()["messages"][1]
    assert environment_message["role"] == "environment"
    assert environment_message["isTruncated"] is True
    assert environment_message["content"] == long_output


class FakeStreamingRunner:
    def __init__(self, resume_event: threading.Event) -> None:
        self.resume_event = resume_event

    async def astream(self, prompt: str, *, callbacks=None, debug: bool = False) -> None:
        del prompt, debug
        if callbacks is None:
            return
        first_chunk = AIMessageChunk(content="Partial", id="assistant-1")
        second_chunk = AIMessageChunk(content=" answer", id="assistant-1")
        for callback in callbacks:
            await callback("messages", first_chunk)
        self.resume_event.wait(timeout=1.0)
        for callback in callbacks:
            await callback("messages", second_chunk)


class ConcurrentStartRuntime(SessionRuntime):
    def start_run(
        self,
        session,
        prompt: str,
        run_options: dict[str, object] | None = None,
    ) -> None:
        del session, prompt, run_options
        raise RuntimeError("Session already has a running task")


class BrokenRunnerFactory:
    def __call__(self, session) -> None:
        del session
        raise RuntimeError("invalid config")


class FakeBlockingRunner:
    def __init__(
        self,
        started_event: threading.Event,
        resume_event: threading.Event,
    ) -> None:
        self.started_event = started_event
        self.resume_event = resume_event

    async def astream(self, prompt: str, *, callbacks=None, debug: bool = False) -> None:
        del prompt, callbacks, debug
        self.started_event.set()
        while not self.resume_event.is_set():
            await asyncio.sleep(0.01)


def test_transcript_keeps_inflight_assistant_draft_across_session_switches(
    session_root: Path,
) -> None:
    resume_event = threading.Event()
    storage = SessionStorage(root=session_root)
    runtime = HostedAgentRuntime(
        storage=storage,
        manager=WebSocketManager(),
        agent_options={},
        runner_factory=lambda _session: FakeStreamingRunner(resume_event),
    )
    client = TestClient(create_app(runtime=runtime))

    _bootstrap(client)
    session_id = client.post("/api/sessions").json()["id"]

    run_response = client.post(
        f"/api/sessions/{session_id}/runs",
        json={"message": "hello"},
    )
    assert run_response.status_code == 200

    partial = _wait_for_transcript_message(client, session_id)
    assert partial["status"] == "running"
    assert partial["messages"][-1]["content"] == "Partial"
    assert partial["messages"][-1]["isStreaming"] is True

    rehydrated_client = TestClient(create_app(runtime=runtime))
    rehydrated_client.cookies.set(
        COOKIE_PRINCIPAL_NAME,
        client.cookies[COOKIE_PRINCIPAL_NAME],
    )
    switched_back = _wait_for_transcript_message(rehydrated_client, session_id)
    assert switched_back["messages"][-1]["content"] == "Partial"
    assert switched_back["messages"][-1]["isStreaming"] is True

    resume_event.set()
    runtime.wait_for_completion(session_id, timeout=1.0)

    completed = client.get(f"/api/sessions/{session_id}/transcript")
    assert completed.status_code == 200
    assert completed.json()["status"] == "idle"
    assert completed.json()["messages"][-1]["content"] == "Partial answer"
    assert completed.json()["messages"][-1]["isStreaming"] is False


def test_run_conflict_marks_session_error(session_root: Path) -> None:
    client = TestClient(create_app(runtime=ConcurrentStartRuntime()))

    _bootstrap(client)
    session_id = client.post("/api/sessions").json()["id"]

    run_response = client.post(
        f"/api/sessions/{session_id}/runs",
        json={"message": "hello"},
    )

    assert run_response.status_code == 409
    assert run_response.json()["detail"] == "Session already has a running task"
    session_response = client.get(f"/api/sessions/{session_id}")
    assert session_response.status_code == 200
    assert session_response.json()["status"] == "error"


def test_hosted_runtime_init_failure_marks_session_error_and_cleans_registry(
    session_root: Path,
) -> None:
    storage = SessionStorage(root=session_root)
    runtime = HostedAgentRuntime(
        storage=storage,
        manager=WebSocketManager(),
        agent_options={},
        runner_factory=BrokenRunnerFactory(),
    )
    client = TestClient(create_app(runtime=runtime))

    _bootstrap(client)
    session_id = client.post("/api/sessions").json()["id"]

    run_response = client.post(
        f"/api/sessions/{session_id}/runs",
        json={"message": "hello"},
    )
    assert run_response.status_code == 200
    runtime.wait_for_completion(session_id, timeout=1.0)

    session_response = client.get(f"/api/sessions/{session_id}")
    assert session_response.status_code == 200
    assert session_response.json()["status"] == "error"

    with runtime._lock:
        assert session_id not in runtime._threads
        assert session_id not in runtime._cancel_events


def test_hosted_runtime_cleans_registry_after_deleted_session_finalizer_error(
    session_root: Path,
) -> None:
    started_event = threading.Event()
    resume_event = threading.Event()
    storage = SessionStorage(root=session_root)
    runtime = HostedAgentRuntime(
        storage=storage,
        manager=WebSocketManager(),
        agent_options={},
        runner_factory=lambda _session: FakeBlockingRunner(started_event, resume_event),
    )
    client = TestClient(create_app(runtime=runtime))

    principal_id = _bootstrap(client)
    session_id = client.post("/api/sessions").json()["id"]
    service = SessionService(principal_id=principal_id, storage=storage)

    run_response = client.post(
        f"/api/sessions/{session_id}/runs",
        json={"message": "hello"},
    )
    assert run_response.status_code == 200
    assert started_event.wait(timeout=1.0)

    service.delete_session(session_id)
    resume_event.set()
    runtime.wait_for_completion(session_id, timeout=1.0)

    with runtime._lock:
        assert session_id not in runtime._threads
        assert session_id not in runtime._cancel_events


def test_workos_pending_user_can_only_see_auth_state(session_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "workos")
    monkeypatch.setenv("AUTH_SECRET", "local-dev-secret")
    monkeypatch.setenv("WORKOS_COOKIE_PASSWORD", _valid_cookie_secret("workos-cookie"))
    monkeypatch.setenv("WORKOS_CLIENT_ID", "client_test")
    monkeypatch.setenv("WORKOS_API_KEY", "sk_test")
    fake_workos = FakeWorkOSClient()
    fake_workos.user_management.add_identity(
        code="pending-code",
        sealed_session="pending-session",
        workos_user_id="wos_user_pending",
        email="pending@example.com",
    )
    client = TestClient(
        create_app(
            runtime=FakeRuntime(session_root),
            workos_client_factory=lambda: fake_workos,
        )
    )

    callback = client.get("/api/auth/callback?code=pending-code", follow_redirects=False)
    assert callback.status_code in {302, 307}

    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["authenticated"] is True
    assert me_response.json()["user"]["status"] == "pending"

    create_response = client.post("/api/sessions")
    assert create_response.status_code == 403
    assert create_response.json()["detail"] == "Approval required"


def test_workos_allowlisted_admin_can_approve_user_and_use_shared_cli_namespace(
    session_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTH_MODE", "workos")
    monkeypatch.setenv("AUTH_SECRET", "local-dev-secret")
    monkeypatch.setenv("WORKOS_COOKIE_PASSWORD", _valid_cookie_secret("workos-cookie"))
    monkeypatch.setenv("WORKOS_CLIENT_ID", "client_test")
    monkeypatch.setenv("WORKOS_API_KEY", "sk_test")
    monkeypatch.setenv("AUTH_BOOTSTRAP_ADMIN_EMAILS", "admin@example.com")
    fake_workos = FakeWorkOSClient()
    fake_workos.user_management.add_identity(
        code="admin-code",
        sealed_session="admin-session",
        workos_user_id="wos_user_admin",
        email="admin@example.com",
    )
    fake_workos.user_management.add_identity(
        code="member-code",
        sealed_session="member-session",
        workos_user_id="wos_user_member",
        email="member@example.com",
    )

    runtime = FakeRuntime(session_root)
    app = create_app(runtime=runtime, workos_client_factory=lambda: fake_workos)
    admin_client = TestClient(app)
    member_client = TestClient(app)

    admin_callback = admin_client.get("/api/auth/callback?code=admin-code", follow_redirects=False)
    member_callback = member_client.get("/api/auth/callback?code=member-code", follow_redirects=False)
    assert admin_callback.status_code in {302, 307}
    assert member_callback.status_code in {302, 307}

    users_response = admin_client.get("/api/admin/users")
    assert users_response.status_code == 200
    member_user = next(item for item in users_response.json() if item["email"] == "member@example.com")

    approve_response = admin_client.post(f"/api/admin/users/{member_user['id']}/approve")
    assert approve_response.status_code == 200

    create_response = member_client.post("/api/sessions")
    assert create_response.status_code == 200
    session_id = create_response.json()["id"]

    token_response = member_client.post(
        "/api/auth/cli/tokens",
        json={"label": "local-cli"},
    )
    assert token_response.status_code == 200
    token_value = token_response.json()["token"]

    cli_list = member_client.get(
        "/api/sessions",
        headers={"Authorization": f"Bearer {token_value}"},
    )
    assert cli_list.status_code == 200
    assert [item["id"] for item in cli_list.json()] == [session_id]


def test_admin_actions_return_404_for_missing_user(
    session_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTH_MODE", "workos")
    monkeypatch.setenv("AUTH_SECRET", "local-dev-secret")
    monkeypatch.setenv("WORKOS_COOKIE_PASSWORD", _valid_cookie_secret("workos-cookie"))
    monkeypatch.setenv("WORKOS_CLIENT_ID", "client_test")
    monkeypatch.setenv("WORKOS_API_KEY", "sk_test")
    monkeypatch.setenv("AUTH_BOOTSTRAP_ADMIN_EMAILS", "admin@example.com")
    fake_workos = FakeWorkOSClient()
    fake_workos.user_management.add_identity(
        code="admin-code",
        sealed_session="admin-session",
        workos_user_id="wos_user_admin",
        email="admin@example.com",
    )

    client = TestClient(
        create_app(
            runtime=FakeRuntime(session_root),
            workos_client_factory=lambda: fake_workos,
        )
    )

    callback = client.get("/api/auth/callback?code=admin-code", follow_redirects=False)
    assert callback.status_code in {302, 307}

    for action in ("approve", "disable"):
        response = client.post(f"/api/admin/users/missing-user/{action}")
        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"

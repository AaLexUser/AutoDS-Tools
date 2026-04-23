from __future__ import annotations

import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk, HumanMessage
from starlette.websockets import WebSocketDisconnect

from autods.sessions import SessionService, TranscriptMessage
from autods_web.api import (
    COOKIE_PRINCIPAL_NAME,
    HostedAgentRuntime,
    SessionRuntime,
    SessionStorage,
    WebSocketManager,
    create_app,
)


class FakeRuntime(SessionRuntime):
    def __init__(self, storage_root: Path) -> None:
        self.storage_root = storage_root
        self.started_runs: list[tuple[str, str, str]] = []
        self.cancelled_sessions: list[str] = []

    def start_run(self, session, prompt: str) -> None:
        self.started_runs.append((session.principal_id, session.id, prompt))
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


@pytest.fixture
def session_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "sessions"
    monkeypatch.setenv("AUTODS_SESSION_HOME", str(root))
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
    assert transcript.json()["messages"][2]["content"] == (
        "I found the relevant files and will inspect them next."
    )


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

    partial = client.get(f"/api/sessions/{session_id}/transcript")
    assert partial.status_code == 200
    assert partial.json()["status"] == "running"
    assert partial.json()["messages"][-1]["content"] == "Partial"
    assert partial.json()["messages"][-1]["isStreaming"] is True

    rehydrated_client = TestClient(create_app(runtime=runtime))
    rehydrated_client.cookies.set(
        COOKIE_PRINCIPAL_NAME,
        client.cookies[COOKIE_PRINCIPAL_NAME],
    )
    switched_back = rehydrated_client.get(f"/api/sessions/{session_id}/transcript")
    assert switched_back.status_code == 200
    assert switched_back.json()["messages"][-1]["content"] == "Partial"
    assert switched_back.json()["messages"][-1]["isStreaming"] is True

    resume_event.set()
    runtime.wait_for_completion(session_id, timeout=1.0)

    completed = client.get(f"/api/sessions/{session_id}/transcript")
    assert completed.status_code == 200
    assert completed.json()["status"] == "idle"
    assert completed.json()["messages"][-1]["content"] == "Partial answer"
    assert completed.json()["messages"][-1]["isStreaming"] is False

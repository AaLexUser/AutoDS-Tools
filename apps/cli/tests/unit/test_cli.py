from __future__ import annotations

import importlib
import json

import httpx
import pytest
from click.testing import CliRunner

from autods_cli.main import HostedApiClient, cli

cli_main = importlib.import_module("autods_cli.main")


def test_cli_help_mentions_server_command() -> None:
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "server" in result.output


def test_exec_without_server_url_autostarts_local_server(
    monkeypatch,
) -> None:
    calls: list[tuple[str, str | None]] = []

    class FakeClient:
        def run_once(
            self,
            message: str,
            session_id: str | None = None,
            options: dict[str, object] | None = None,
        ) -> str:
            del session_id
            calls.append(("run_once", message))
            assert options is not None
            return "session-123"

        def stream_session_until_idle(self, session_id: str, **_kwargs) -> int:
            calls.append(("stream", session_id))
            return 0

    def fake_build_runtime(_cli_opts, *, server_url, api_host, api_port):
        calls.append(("runtime", server_url))
        return cli_main.CliRuntime(
            server_url=f"http://{api_host}:{api_port}",
            principal_token="principal-token",
            started_local=True,
            client=FakeClient(),
        )

    monkeypatch.setattr(cli_main, "build_cli_runtime", fake_build_runtime)

    result = CliRunner().invoke(cli, ["exec", "hello world"])

    assert result.exit_code == 0
    assert ("runtime", None) in calls
    assert ("run_once", "hello world") in calls


def test_exec_with_server_url_skips_local_autostart(monkeypatch) -> None:
    calls: list[tuple[str, str | None]] = []

    class FakeClient:
        def run_once(
            self,
            message: str,
            session_id: str | None = None,
            options: dict[str, object] | None = None,
        ) -> str:
            del session_id
            calls.append(("run_once", message))
            assert options is not None
            return "session-456"

        def stream_session_until_idle(self, session_id: str, **_kwargs) -> int:
            calls.append(("stream", session_id))
            return 0

    def fake_build_runtime(_cli_opts, *, server_url, api_host, api_port):
        calls.append(("runtime", server_url))
        return cli_main.CliRuntime(
            server_url=server_url,
            principal_token="principal-token",
            started_local=False,
            client=FakeClient(),
        )

    monkeypatch.setattr(cli_main, "build_cli_runtime", fake_build_runtime)

    result = CliRunner().invoke(
        cli,
        ["exec", "hello world", "--server-url", "http://example.com"],
    )

    assert result.exit_code == 0
    assert ("runtime", "http://example.com") in calls
    assert ("run_once", "hello world") in calls


def test_hosted_client_start_run_sends_options_in_request_body() -> None:
    request_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/sessions/session-123/runs":
            request_payloads.append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                200,
                json={"session_id": "session-123", "status": "started"},
            )
        pytest.fail(f"Unexpected request path: {request.url.path}")

    client = HostedApiClient(
        "http://example.com",
        "principal-token",
        client=httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="http://example.com",
            headers={"X-AutoDS-Principal": "principal-token"},
        ),
    )

    client.start_run(
        "session-123",
        "hello",
        options={"project_path": "/tmp/project", "model": "gpt-5"},
    )

    assert request_payloads == [
        {
            "message": "hello",
            "options": {"project_path": "/tmp/project", "model": "gpt-5"},
        }
    ]


def test_stream_session_until_idle_renders_finalized_streaming_message(
    monkeypatch,
) -> None:
    seen_paths: list[str] = []
    rendered_messages: list[list[str]] = []
    transcript_payloads = [
        {
            "session_id": "session-123",
            "status": "running",
            "messages": [
                {
                    "id": "assistant-1",
                    "role": "assistant",
                    "content": "partial",
                    "timestamp": "2026-04-14T10:00:00+00:00",
                    "isStreaming": True,
                }
            ],
        },
        {
            "session_id": "session-123",
            "status": "idle",
            "messages": [
                {
                    "id": "assistant-1",
                    "role": "assistant",
                    "content": "partial done",
                    "timestamp": "2026-04-14T10:00:01+00:00",
                    "isStreaming": False,
                },
            ],
        },
    ]

    def fake_render_messages(messages, *, include_user: bool = False) -> None:
        del include_user
        rendered_messages.append([message.content for message in messages])

    monkeypatch.setattr(cli_main, "render_messages", fake_render_messages)

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        if request.url.path == "/api/sessions/session-123/transcript":
            payload = transcript_payloads.pop(0)
            return httpx.Response(200, json=payload)
        pytest.fail(f"Unexpected request path: {request.url.path}")

    client = HostedApiClient(
        "http://example.com",
        "principal-token",
        client=httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="http://example.com",
            headers={"X-AutoDS-Principal": "principal-token"},
        ),
    )

    seen_count = client.stream_session_until_idle("session-123", poll_interval=0)

    assert seen_count == 1
    assert rendered_messages == [["partial done"]]
    assert seen_paths == [
        "/api/sessions/session-123/transcript",
        "/api/sessions/session-123/transcript",
    ]


def test_hosted_client_can_use_authorization_header() -> None:
    seen_headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers.get("Authorization"))
        return httpx.Response(200, json=[])

    client = HostedApiClient(
        "http://example.com",
        "Bearer test-token",
        auth_header_name="Authorization",
        client=httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="http://example.com",
            headers={"Authorization": "Bearer test-token"},
        ),
    )

    sessions = client.list_sessions()

    assert sessions == []
    assert seen_headers == ["Bearer test-token"]

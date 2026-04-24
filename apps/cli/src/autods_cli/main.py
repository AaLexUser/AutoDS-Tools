from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol

import click
import httpx
from dotenv import load_dotenv
from pydantic import BaseModel
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from autods.constants import AUTODS_HOME
from autods.logging import setup_logging
from autods_web.server import start_web_server

_ = load_dotenv()

console = Console()

DEFAULT_LOCAL_HOST = "127.0.0.1"
DEFAULT_LOCAL_PORT = 8000
DEFAULT_SERVER_URL_ENV = "AUTODS_SERVER_URL"
PRINCIPAL_TOKEN_ENV = "AUTODS_PRINCIPAL_TOKEN"
PRINCIPAL_TOKEN_PATH = AUTODS_HOME / "cli_principal_token"
PRINCIPAL_HEADER = "X-AutoDS-Principal"
API_TOKEN_ENV = "AUTODS_API_TOKEN"
API_TOKEN_PATH = AUTODS_HOME / "cli_api_token"
AUTHORIZATION_HEADER = "Authorization"


class AgentCLIOptions(BaseModel):
    provider: Optional[str]
    model: Optional[str]
    model_base_url: Optional[str]
    api_key: Optional[str]
    max_steps: Optional[int]
    project_path: Optional[str]
    config_file: Optional[str]
    trace_debug: bool = False
    trace_file: Optional[str] = None

    @staticmethod
    def agent_options(func):
        options = [
            click.option("--provider", "-p", help="LLM provider to use"),
            click.option("--model", "-m", help="Specific model to use"),
            click.option("--model-base-url", help="Base URL for the model API"),
            click.option("--api-key", "-k", help="API key override"),
            click.option(
                "--max-steps", type=int, help="Maximum LangGraph recursion steps"
            ),
            click.option("--config-file", help="Path to configuration file"),
            click.option(
                "--trace-debug", is_flag=True, help="Enable debug tracing on the server"
            ),
            click.option(
                "--trace-file",
                type=click.Path(dir_okay=False, path_type=Path),
                help="Trace file path for server-side debugging",
            ),
        ]
        for option in reversed(options):
            func = option(func)
        return func

    @classmethod
    def from_args(cls, kwargs: dict[str, Any]) -> "AgentCLIOptions":
        def _normalize(value: Any) -> Any:
            if value is None:
                return None
            if isinstance(value, (str, Path, os.PathLike)):
                return str(value)
            return value

        return cls(
            provider=_normalize(kwargs.get("provider")),
            model=_normalize(kwargs.get("model")),
            model_base_url=_normalize(kwargs.get("model_base_url")),
            api_key=_normalize(kwargs.get("api_key")),
            max_steps=_normalize(kwargs.get("max_steps")),
            project_path=_normalize(kwargs.get("project_path")),
            config_file=_normalize(kwargs.get("config_file")),
            trace_debug=bool(kwargs.get("trace_debug", False)),
            trace_file=_normalize(kwargs.get("trace_file")),
        )


class RemoteSession(BaseModel):
    id: str
    created_at: str
    updated_at: str
    status: str
    folder_size: int = 0


class TranscriptMessageModel(BaseModel):
    id: str
    role: str
    content: str
    timestamp: str
    isStreaming: bool = False
    isTruncated: bool = False


class TranscriptModel(BaseModel):
    session_id: str
    status: str
    messages: list[TranscriptMessageModel]


class SessionClient(Protocol):
    def create_session(self) -> RemoteSession: ...
    def list_sessions(self) -> list[RemoteSession]: ...
    def get_session(self, session_id: str) -> RemoteSession: ...
    def get_transcript(self, session_id: str) -> TranscriptModel: ...
    def cancel_session(self, session_id: str) -> None: ...
    def run_once(
        self,
        message: str,
        session_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> str: ...
    def stream_session_until_idle(
        self,
        session_id: str,
        *,
        seen_messages: int = 0,
        include_user: bool = False,
        poll_interval: float = 0.25,
    ) -> int: ...


@dataclass(frozen=True)
class CliRuntime:
    server_url: str
    principal_token: str
    started_local: bool
    client: SessionClient


def common_options(func):
    options = [
        click.option(
            "--file",
            "-f",
            "file_path",
            help="Path to file containing the task/input description.",
        ),
        click.option(
            "--project-path", "-w", help="Project workspace path for the agent."
        ),
        click.option(
            "--server-url",
            help="Hosted API base URL. Defaults to AUTODS_SERVER_URL or local auto-start.",
        ),
        click.option(
            "--api-host",
            default=DEFAULT_LOCAL_HOST,
            help="Local API host for auto-start.",
        ),
        click.option(
            "--api-port",
            default=DEFAULT_LOCAL_PORT,
            type=int,
            help="Local API port for auto-start.",
        ),
    ]
    for option in reversed(options):
        func = option(func)
    return func


def _handle_task_input(task: Optional[str], file_path: Optional[str]) -> str:
    if file_path and task:
        raise click.ClickException("Provide either inline task or --file, not both")
    if file_path:
        path = Path(file_path)
        if not path.exists():
            raise click.ClickException(f"File not found: {file_path}")
        return path.read_text().strip()
    if not task:
        raise click.ClickException("Task is required")
    return task


def build_server_options(cli_opts: AgentCLIOptions) -> dict[str, Any]:
    agent_options = {
        "provider": cli_opts.provider,
        "model": cli_opts.model,
        "model_base_url": cli_opts.model_base_url,
        "api_key": cli_opts.api_key,
        "max_steps": cli_opts.max_steps,
        "config_file": cli_opts.config_file,
        "project_path": cli_opts.project_path,
        "trace_debug": cli_opts.trace_debug,
        "trace_file": cli_opts.trace_file,
    }
    return {key: value for key, value in agent_options.items() if value is not None}


def load_or_create_principal_token() -> str:
    env_token = os.environ.get(PRINCIPAL_TOKEN_ENV)
    if env_token:
        return env_token
    PRINCIPAL_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    if PRINCIPAL_TOKEN_PATH.exists():
        return PRINCIPAL_TOKEN_PATH.read_text().strip()
    token = f"cli-{secrets.token_urlsafe(24)}"
    PRINCIPAL_TOKEN_PATH.write_text(token)
    return token


def load_api_token() -> str | None:
    env_token = os.environ.get(API_TOKEN_ENV)
    if env_token:
        return env_token.strip()
    if API_TOKEN_PATH.exists():
        token = API_TOKEN_PATH.read_text().strip()
        return token or None
    return None


def is_server_healthy(server_url: str, principal_token: str) -> bool:
    try:
        response = httpx.get(
            f"{server_url.rstrip('/')}/health",
            headers={PRINCIPAL_HEADER: principal_token},
            timeout=1.0,
        )
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def wait_for_server(
    server_url: str, principal_token: str, timeout_s: float = 10.0
) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if is_server_healthy(server_url, principal_token):
            return
        time.sleep(0.2)
    raise click.ClickException(f"Server did not become healthy at {server_url}")


def prepare_cli_connection(
    server_url: str | None,
    *,
    api_host: str = DEFAULT_LOCAL_HOST,
    api_port: int = DEFAULT_LOCAL_PORT,
    agent_options: dict[str, Any] | None = None,
) -> tuple[str, str, bool]:
    resolved_url = server_url or os.environ.get(DEFAULT_SERVER_URL_ENV)
    principal_token = load_or_create_principal_token()

    if resolved_url:
        return resolved_url.rstrip("/"), principal_token, False

    local_url = f"http://{api_host}:{api_port}"
    if is_server_healthy(local_url, principal_token):
        return local_url, principal_token, False

    process = start_web_server(
        api_host,
        api_port,
        background=True,
        agent_options=agent_options or {},
    )
    if process is None:
        raise click.ClickException("Failed to start local AutoDS server")
    wait_for_server(local_url, principal_token)
    return local_url, principal_token, True


class HostedApiClient:
    def __init__(
        self,
        server_url: str,
        principal_token: str,
        auth_header_name: str = PRINCIPAL_HEADER,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.principal_token = principal_token
        self.auth_header_name = auth_header_name
        self._client = client or httpx.Client(
            base_url=self.server_url,
            headers={auth_header_name: principal_token},
            timeout=timeout,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = self._client.request(method, path, **kwargs)
        if response.is_success:
            return response
        detail = (
            response.text.strip()
            or f"Request failed with status {response.status_code}"
        )
        raise click.ClickException(detail)

    def create_session(self) -> RemoteSession:
        response = self._request("POST", "/api/sessions")
        return RemoteSession.model_validate(response.json())

    def list_sessions(self) -> list[RemoteSession]:
        response = self._request("GET", "/api/sessions")
        return [RemoteSession.model_validate(item) for item in response.json()]

    def get_session(self, session_id: str) -> RemoteSession:
        response = self._request("GET", f"/api/sessions/{session_id}")
        return RemoteSession.model_validate(response.json())

    def get_transcript(self, session_id: str) -> TranscriptModel:
        response = self._request("GET", f"/api/sessions/{session_id}/transcript")
        return TranscriptModel.model_validate(response.json())

    def start_run(
        self,
        session_id: str,
        message: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {"message": message}
        if options:
            payload["options"] = options
        self._request(
            "POST",
            f"/api/sessions/{session_id}/runs",
            json=payload,
        )

    def cancel_session(self, session_id: str) -> None:
        self._request("POST", f"/api/sessions/{session_id}/cancel")

    def run_once(
        self,
        message: str,
        session_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        selected_session = session_id or self.create_session().id
        self.start_run(selected_session, message, options=options)
        return selected_session

    def stream_session_until_idle(
        self,
        session_id: str,
        *,
        seen_messages: int = 0,
        include_user: bool = False,
        poll_interval: float = 0.5,
    ) -> int:
        stream_start_index = seen_messages
        rendered_ids: set[str] = set()
        while True:
            transcript = self.get_transcript(session_id)
            render_batch: list[TranscriptMessageModel] = []
            for message in transcript.messages[stream_start_index:]:
                if message.id in rendered_ids:
                    continue
                if message.role == "assistant" and message.isStreaming:
                    continue
                render_batch.append(message)
                rendered_ids.add(message.id)
            if render_batch:
                render_messages(render_batch, include_user=include_user)
            seen_messages = len(transcript.messages)

            if transcript.status == "idle":
                return seen_messages
            if transcript.status == "error":
                raise click.ClickException(f"Session {session_id} ended in error")
            time.sleep(poll_interval)


def render_messages(
    messages: list[TranscriptMessageModel],
    *,
    include_user: bool = False,
) -> None:
    for message in messages:
        if message.role == "user" and not include_user:
            continue
        if message.role == "assistant":
            console.print(message.content)
            continue
        if message.role == "environment":
            console.print(f"[dim]{message.content}[/dim]")
            continue
        console.print(f"[cyan]You:[/cyan] {message.content}")


def _print_sessions_table(sessions: list[RemoteSession]) -> None:
    table = Table(title="Saved sessions")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Session ID", style="green")
    table.add_column("Status")
    table.add_column("Updated")
    for index, session in enumerate(sessions, start=1):
        table.add_row(str(index), session.id, session.status, session.updated_at)
    console.print(table)


def _prompt_for_session_selection(sessions: list[RemoteSession]) -> RemoteSession:
    if not sessions:
        raise click.ClickException("No sessions available to resume")
    max_display = min(len(sessions), 10)
    display_sessions = sessions[:max_display]
    _print_sessions_table(display_sessions)
    choice = Prompt.ask(
        "Select session", choices=[str(i) for i in range(1, max_display + 1)]
    )
    return display_sessions[int(choice) - 1]


def build_cli_runtime(
    cli_opts: AgentCLIOptions,
    *,
    server_url: str | None,
    api_host: str,
    api_port: int,
) -> CliRuntime:
    resolved_url, principal_token, started_local = prepare_cli_connection(
        server_url,
        api_host=api_host,
        api_port=api_port,
        agent_options=build_server_options(cli_opts),
    )
    auth_header_name = PRINCIPAL_HEADER
    auth_value = principal_token
    if server_url or os.environ.get(DEFAULT_SERVER_URL_ENV):
        api_token = load_api_token()
        if api_token:
            auth_header_name = AUTHORIZATION_HEADER
            auth_value = f"Bearer {api_token}"
        elif os.environ.get("AUTH_MODE", "disabled").strip().lower() == "workos":
            raise click.ClickException(
                "Hosted auth requires a CLI API token. Create one in the browser admin page and save it with `autods auth set-token`."
            )
    return CliRuntime(
        server_url=resolved_url,
        principal_token=auth_value,
        started_local=started_local,
        client=HostedApiClient(
            resolved_url,
            auth_value,
            auth_header_name=auth_header_name,
        ),
    )


@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Autods Agent - hosted client and local server entrypoint."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(chat)


@cli.group()
def auth() -> None:
    """Manage hosted CLI authentication."""


@auth.command("set-token")
@click.argument("token")
def auth_set_token(token: str) -> None:
    API_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    API_TOKEN_PATH.write_text(token.strip())
    console.print(f"[dim]Saved CLI token to {API_TOKEN_PATH}[/dim]")


@auth.command("clear-token")
def auth_clear_token() -> None:
    if API_TOKEN_PATH.exists():
        API_TOKEN_PATH.unlink()
    console.print(f"[dim]Cleared CLI token from {API_TOKEN_PATH}[/dim]")


@AgentCLIOptions.agent_options
@common_options
@cli.command()
@click.argument("task", required=False)
@click.option("--session-id", help="Run inside an existing hosted session.")
def exec(
    task: str | None,
    file_path: str | None,
    session_id: str | None,
    server_url: str | None,
    api_host: str,
    api_port: int,
    **kwargs: Any,
) -> None:
    """Execute a single task against the hosted session service."""
    cli_opts = AgentCLIOptions.from_args(kwargs)
    run_options = build_server_options(cli_opts)
    runtime = build_cli_runtime(
        cli_opts,
        server_url=server_url,
        api_host=api_host,
        api_port=api_port,
    )
    if runtime.started_local:
        console.print(f"[dim]Started local AutoDS server at {runtime.server_url}[/dim]")
    inline_task = _handle_task_input(task, file_path)
    selected_session = runtime.client.run_once(
        inline_task,
        session_id=session_id,
        options=run_options,
    )
    runtime.client.stream_session_until_idle(selected_session)
    console.print(f"[dim]Session: {selected_session}[/dim]")


@AgentCLIOptions.agent_options
@common_options
@cli.command()
def chat(
    file_path: str | None = None,
    project_path: str | None = None,
    server_url: str | None = None,
    api_host: str = DEFAULT_LOCAL_HOST,
    api_port: int = DEFAULT_LOCAL_PORT,
    **kwargs: Any,
) -> None:
    """Start an interactive chat against the hosted server."""
    cli_opts = AgentCLIOptions.from_args({**kwargs, "project_path": project_path})
    run_options = build_server_options(cli_opts)
    runtime = build_cli_runtime(
        cli_opts,
        server_url=server_url,
        api_host=api_host,
        api_port=api_port,
    )
    if runtime.started_local:
        console.print(f"[dim]Started local AutoDS server at {runtime.server_url}[/dim]")
    session_id = runtime.client.create_session().id
    seen_messages = 0

    while True:
        try:
            message = Prompt.ask(">")
        except (EOFError, KeyboardInterrupt):
            console.print()
            return
        if not isinstance(message, str):
            continue
        stripped = message.strip()
        if not stripped:
            continue
        if stripped in {"exit", "quit"}:
            return

        runtime.client.run_once(stripped, session_id=session_id, options=run_options)
        seen_messages = runtime.client.stream_session_until_idle(
            session_id,
            seen_messages=seen_messages,
        )


@AgentCLIOptions.agent_options
@common_options
@cli.command()
@click.argument("session_id", required=False)
def resume(
    session_id: str | None,
    file_path: str | None,
    project_path: str | None,
    server_url: str | None,
    api_host: str,
    api_port: int,
    **kwargs: Any,
) -> None:
    """Resume an existing hosted session."""
    cli_opts = AgentCLIOptions.from_args({**kwargs, "project_path": project_path})
    run_options = build_server_options(cli_opts)
    runtime = build_cli_runtime(
        cli_opts,
        server_url=server_url,
        api_host=api_host,
        api_port=api_port,
    )
    if runtime.started_local:
        console.print(f"[dim]Started local AutoDS server at {runtime.server_url}[/dim]")
    sessions = runtime.client.list_sessions()
    selected = (
        runtime.client.get_session(session_id)
        if session_id
        else _prompt_for_session_selection(sessions)
    )

    transcript = runtime.client.get_transcript(selected.id)
    if transcript.messages:
        render_messages(transcript.messages, include_user=True)
    seen_messages = len(transcript.messages)

    while True:
        try:
            message = Prompt.ask(">")
        except (EOFError, KeyboardInterrupt):
            console.print()
            return
        if not isinstance(message, str):
            continue
        stripped = message.strip()
        if not stripped:
            continue
        if stripped in {"exit", "quit"}:
            return

        runtime.client.run_once(
            stripped,
            session_id=selected.id,
            options=run_options,
        )
        seen_messages = runtime.client.stream_session_until_idle(
            selected.id,
            seen_messages=seen_messages,
        )


def _run_server_command(
    api_host: str,
    api_port: int,
    background: bool,
    cli_opts: AgentCLIOptions,
) -> None:
    agent_options = build_server_options(cli_opts)
    process = start_web_server(
        api_host,
        api_port,
        background=background,
        agent_options=agent_options,
    )
    if background:
        if process is None:
            raise click.ClickException("Failed to start API server")
        console.print(f"API: http://{api_host}:{api_port}")


@AgentCLIOptions.agent_options
@cli.command(name="server")
@click.option("--api-host", default=DEFAULT_LOCAL_HOST, help="API server host")
@click.option(
    "--api-port", default=DEFAULT_LOCAL_PORT, type=int, help="API server port"
)
@click.option("--background", is_flag=True, help="Run API server in background")
def server(api_host: str, api_port: int, background: bool, **kwargs: Any) -> None:
    """Start the hosted AutoDS API server explicitly."""
    _run_server_command(
        api_host, api_port, background, AgentCLIOptions.from_args(kwargs)
    )


@AgentCLIOptions.agent_options
@cli.command(name="web", hidden=True)
@click.option("--api-host", default=DEFAULT_LOCAL_HOST, help="API server host")
@click.option(
    "--api-port", default=DEFAULT_LOCAL_PORT, type=int, help="API server port"
)
@click.option("--background", is_flag=True, help="Run API server in background")
def web(api_host: str, api_port: int, background: bool, **kwargs: Any) -> None:
    _run_server_command(
        api_host, api_port, background, AgentCLIOptions.from_args(kwargs)
    )


def main() -> None:
    """Entry point for the autods CLI."""
    setup_logging(console=False)
    cli()

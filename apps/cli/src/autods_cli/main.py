from __future__ import annotations

import secrets
import time
from pathlib import Path
from typing import Any

import click
import requests
from rich.console import Console

from autods.constants import AUTODS_HOME
from autods_web.server import start_web_server

console = Console()
PRINCIPAL_FILE = AUTODS_HOME / "cli_principal"


def principal_id() -> str:
    PRINCIPAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    if PRINCIPAL_FILE.exists():
        value = PRINCIPAL_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_urlsafe(24)
    PRINCIPAL_FILE.write_text(value, encoding="utf-8")
    return value


class Client:
    def __init__(self, url: str):
        self.url = url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"X-AutoDS-Principal": principal_id()})

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.session.request(method, f"{self.url}{path}", timeout=30, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else None

    def create_session(self) -> str:
        return str(self.request("POST", "/api/sessions")["id"])

    def run(self, session_id: str, message: str) -> None:
        self.request("POST", f"/api/sessions/{session_id}/runs", json={"message": message})

    def transcript(self, session_id: str) -> dict[str, Any]:
        return self.request("GET", f"/api/sessions/{session_id}/transcript")


def wait_for_server(url: str, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            requests.get(f"{url.rstrip('/')}/health", timeout=1).raise_for_status()
            return
        except requests.RequestException:
            time.sleep(0.2)
    raise click.ClickException(f"Server did not start at {url}")


def read_task(task: str | None, file: str | None) -> str:
    if file:
        return Path(file).read_text(encoding="utf-8")
    if task:
        return task
    raise click.ClickException("Provide a task argument or --file")


def print_transcript(snapshot: dict[str, Any], seen: set[str]) -> None:
    for message in snapshot.get("messages", []):
        msg_id = str(message.get("id"))
        if msg_id in seen:
            continue
        seen.add(msg_id)
        role = message.get("role", "message")
        content = str(message.get("content", "")).strip()
        if content:
            console.print(f"[bold]{role}[/bold]: {content}")


@click.group()
def cli() -> None:
    """AutoDS demo CLI."""


@cli.command("exec")
@click.argument("task", required=False)
@click.option("--file", "file_path")
@click.option("--server-url")
@click.option("--api-host", default="localhost", show_default=True)
@click.option("--api-port", default=8000, show_default=True)
def exec_cmd(task: str | None, file_path: str | None, server_url: str | None, api_host: str, api_port: int) -> None:
    message = read_task(task, file_path)
    url = server_url or f"http://{api_host}:{api_port}"
    process = None
    if server_url is None:
        process = start_web_server(api_host=api_host, api_port=api_port, background=True)
        wait_for_server(url)
    try:
        client = Client(url)
        session_id = client.create_session()
        client.run(session_id, message)
        seen: set[str] = set()
        while True:
            snapshot = client.transcript(session_id)
            print_transcript(snapshot, seen)
            if snapshot.get("status") in {"idle", "error"}:
                break
            time.sleep(1)
    finally:
        if process is not None:
            process.terminate()


@cli.command()
@click.option("--api-host", default="localhost", show_default=True)
@click.option("--api-port", default=8000, show_default=True)
def server(api_host: str, api_port: int) -> None:
    start_web_server(api_host=api_host, api_port=api_port)


def main() -> None:
    cli()

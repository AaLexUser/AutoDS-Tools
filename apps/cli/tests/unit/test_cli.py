from __future__ import annotations

import importlib

from click.testing import CliRunner

from autods_cli.main import cli, read_task

cli_main = importlib.import_module("autods_cli.main")


def test_cli_help_mentions_server_command() -> None:
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "server" in result.output


def test_read_task_accepts_inline_task() -> None:
    assert read_task("hello", None) == "hello"


def test_principal_id_creates_token_file(tmp_path, monkeypatch) -> None:
    token_path = tmp_path / "principal"
    monkeypatch.setattr(cli_main, "PRINCIPAL_FILE", token_path)

    first = cli_main.principal_id()
    second = cli_main.principal_id()

    assert first
    assert second == first
    assert token_path.read_text(encoding="utf-8") == first

from click.testing import CliRunner

from autods_cli.main import cli


def test_cli_help() -> None:
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "Autods Agent" in result.output

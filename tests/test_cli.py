from typer.testing import CliRunner

from receipts_merger.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout == "0.1.0\n"


def test_help_without_arguments() -> None:
    result = runner.invoke(app)

    assert result.exit_code == 2
    assert "Usage:" in result.stdout

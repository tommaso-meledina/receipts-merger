from typing import Annotated

import typer

from receipts_merger import __version__

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


def print_version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit


@app.callback()
def cli(
    version: Annotated[
        bool,
        typer.Option("--version", callback=print_version, is_eager=True, help="Show the version."),
    ] = False,
) -> None:
    pass


def main() -> None:
    app()

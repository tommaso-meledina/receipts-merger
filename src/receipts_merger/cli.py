from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from receipts_merger import __version__
from receipts_merger.application import PipelineError, run_pipeline
from receipts_merger.config import AppConfig
from receipts_merger.documents import DocumentError
from receipts_merger.extraction import ExtractionError
from receipts_merger.rendering import RenderingError
from receipts_merger.review import OverrideError

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


@app.command()
def run(
    input_directory: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            readable=True,
            resolve_path=True,
            help="Directory containing receipt and statement PDFs.",
        ),
    ],
    output_directory: Annotated[
        Path,
        typer.Option("--output", "-o", help="Directory for composites and the manifest."),
    ],
    statement: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            help="Statement PDF when automatic detection is ambiguous.",
        ),
    ] = None,
    config_path: Annotated[
        Path | None,
        typer.Option(
            "--config",
            exists=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            help="Optional TOML configuration.",
        ),
    ] = None,
    overrides: Annotated[
        Path | None,
        typer.Option(
            exists=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            help="Optional JSON review overrides.",
        ),
    ] = None,
    include_same_currency: Annotated[
        bool,
        typer.Option(help="Enhance accepted same-currency matches too."),
    ] = False,
) -> None:
    try:
        config = AppConfig.from_toml(config_path) if config_path else AppConfig()
        summary = run_pipeline(
            input_directory,
            output_directory,
            config,
            statement_path=statement,
            overrides_path=overrides,
            include_same_currency=include_same_currency,
        )
    except (
        DocumentError,
        ExtractionError,
        OverrideError,
        PipelineError,
        RenderingError,
        ValidationError,
        OSError,
    ) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error

    typer.echo(
        f"Processed {summary.receipts} receipts: "
        f"{summary.accepted} accepted, "
        f"{summary.ambiguous} ambiguous, "
        f"{summary.unmatched} unmatched; "
        f"{summary.enhanced} enhanced, "
        f"{summary.copied} copied unchanged."
    )


def main() -> None:
    app()

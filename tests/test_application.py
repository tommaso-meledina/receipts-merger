from pathlib import Path

from pypdf import PdfReader

from receipts_merger.application import run_pipeline
from receipts_merger.config import AppConfig
from receipts_merger.manifest import read_manifest
from receipts_merger.models import MatchStatus
from tests.helpers import write_pdf


def test_run_end_to_end_with_synthetic_pdfs(tmp_path: Path) -> None:
    input_directory = tmp_path / "input"
    output_directory = tmp_path / "output"
    input_directory.mkdir()
    receipt_path = input_directory / "receipt.pdf"
    statement_path = input_directory / "statement.pdf"
    write_pdf(
        receipt_path,
        ("Example Taxi", "Date 16/06/2026", "Total USD 12.34"),
    )
    write_pdf(
        statement_path,
        (
            "Card statement",
            "16/06/2026 EXAMPLE TAXI USD 12.34 EUR 11.42",
        ),
    )

    summary = run_pipeline(
        input_directory,
        output_directory,
        AppConfig(),
        statement_path=statement_path,
    )

    assert summary.receipts == 1
    assert summary.accepted == 1
    composites = tuple(output_directory.glob("*-composite.pdf"))
    assert len(composites) == 1
    assert len(PdfReader(composites[0]).pages) == 2
    manifest = read_manifest(output_directory / "manifest.json")
    assert manifest.decisions[0].status is MatchStatus.ACCEPTED

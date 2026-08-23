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
    unmatched_path = input_directory / "unmatched.pdf"
    statement_path = input_directory / "statement.pdf"
    write_pdf(
        receipt_path,
        ("Example Taxi", "Date 16/06/2026", "Total USD 12.34"),
    )
    write_pdf(
        unmatched_path,
        ("Other Shop", "Date 16/06/2026", "Total GBP 99.99"),
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

    assert summary.receipts == 2
    assert summary.accepted == 1
    assert summary.enhanced == 1
    assert summary.copied == 1
    output_pdfs = {path.name for path in output_directory.glob("*.pdf")}
    assert output_pdfs == {"receipt.pdf", "unmatched.pdf"}
    composite = PdfReader(output_directory / receipt_path.name)
    assert len(composite.pages) == 2
    assert composite.pages[1].extract_text() in (None, "")
    assert (output_directory / unmatched_path.name).read_bytes() == unmatched_path.read_bytes()
    manifest = read_manifest(output_directory / "manifest.json")
    assert any(decision.status is MatchStatus.ACCEPTED for decision in manifest.decisions)
    receipt_document = next(
        document for document in manifest.documents if document.path == receipt_path.resolve()
    )
    stale_path = output_directory / f"{receipt_path.stem}-{receipt_document.id[:8]}-composite.pdf"
    stale_path.write_bytes(b"stale")

    run_pipeline(
        input_directory,
        output_directory,
        AppConfig(),
        statement_path=statement_path,
    )

    assert not stale_path.exists()


def test_same_currency_is_copied_unless_included(tmp_path: Path) -> None:
    input_directory = tmp_path / "input"
    output_directory = tmp_path / "output"
    included_output_directory = tmp_path / "included-output"
    input_directory.mkdir()
    receipt_path = input_directory / "receipt.pdf"
    statement_path = input_directory / "statement.pdf"
    write_pdf(
        receipt_path,
        ("Example Taxi", "Date 16/06/2026", "Total EUR 11.42"),
    )
    write_pdf(
        statement_path,
        ("Card statement", "16/06/2026 EXAMPLE TAXI EUR 11.42"),
    )

    default_summary = run_pipeline(
        input_directory,
        output_directory,
        AppConfig(),
        statement_path=statement_path,
    )
    included_summary = run_pipeline(
        input_directory,
        included_output_directory,
        AppConfig(),
        statement_path=statement_path,
        include_same_currency=True,
    )

    assert default_summary.accepted == 1
    assert default_summary.enhanced == 0
    assert default_summary.copied == 1
    assert (output_directory / receipt_path.name).read_bytes() == receipt_path.read_bytes()
    assert included_summary.enhanced == 1
    assert included_summary.copied == 0
    assert len(PdfReader(included_output_directory / receipt_path.name).pages) == 2

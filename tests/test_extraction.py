import logging
from pathlib import Path

import ocrmypdf
import pytest

from receipts_merger.config import OcrConfig
from receipts_merger.documents import DocumentError, discover_pdfs, inventory_document
from receipts_merger.extraction import _run_ocr, extract_document
from receipts_merger.models import DocumentKind
from tests.helpers import write_pdf


def test_discover_pdfs_is_sorted(tmp_path: Path) -> None:
    write_pdf(tmp_path / "b.pdf", ("Second",))
    write_pdf(tmp_path / "A.pdf", ("First",))
    (tmp_path / "notes.txt").write_text("ignored")

    assert [path.name for path in discover_pdfs(tmp_path)] == ["A.pdf", "b.pdf"]


def test_discover_pdfs_requires_input(tmp_path: Path) -> None:
    with pytest.raises(DocumentError, match="contains no PDF"):
        discover_pdfs(tmp_path)


def test_inventory_uses_content_hash(tmp_path: Path) -> None:
    path = tmp_path / "receipt.pdf"
    write_pdf(path, ("Example",))

    document = inventory_document(path)

    assert len(document.id) == 64
    assert document.page_count == 1
    assert document.kind is DocumentKind.UNKNOWN


def test_extract_native_text_without_ocr(tmp_path: Path) -> None:
    path = tmp_path / "receipt.pdf"
    write_pdf(path, ("Example Merchant", "16/06/2026", "Total EUR 12.34"))

    extracted = extract_document(
        path,
        tmp_path / "work",
        OcrConfig(minimum_text_characters=1),
    )

    assert extracted.ocr_applied is False
    assert extracted.document.kind is DocumentKind.RECEIPT
    assert "Example" in extracted.pages[0].text


def test_ocr_warnings_include_input_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_path = tmp_path / "scanned receipt.pdf"
    logger = logging.getLogger("ocrmypdf")
    previous_handlers = logger.handlers[:]

    def fake_ocr(*args: object, **kwargs: object) -> ocrmypdf.ExitCode:
        logging.getLogger("ocrmypdf._exec.tesseract").warning("possibly poor OCR")
        logging.getLogger("ocrmypdf.optimize").warning("image left unchanged")
        return ocrmypdf.ExitCode.ok

    monkeypatch.setattr("receipts_merger.extraction.ocrmypdf.ocr", fake_ocr)

    _run_ocr(input_path, tmp_path / "work" / "output.pdf", OcrConfig())

    stderr = capsys.readouterr().err
    assert f"[OCR {input_path}] possibly poor OCR" in stderr
    assert f"[OCR {input_path}] image left unchanged" in stderr
    assert logger.handlers == previous_handlers

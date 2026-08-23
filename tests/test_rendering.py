from pathlib import Path

import pypdfium2 as pdfium
import pytest
from pypdf import PdfReader

from receipts_merger.models import (
    BoundingBox,
    MatchDecision,
    MatchStatus,
    SourceSpan,
    StatementRow,
)
from receipts_merger.rendering import RenderingError, render_composite
from tests.helpers import write_pdf, write_pdf_pages
from tests.test_matching import make_row


def test_render_only_relevant_page_with_permanent_redaction(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.pdf"
    statement_path = tmp_path / "statement.pdf"
    output_path = tmp_path / "output.pdf"
    write_pdf(receipt_path, ("Receipt",))
    write_pdf_pages(
        statement_path,
        (
            ("Unrelated page",),
            ("Statement heading", "SELECTED TRANSACTION", "UNRELATED TRANSACTION"),
        ),
    )
    selected = row_with_box(
        "selected",
        page_index=1,
        text="SELECTED TRANSACTION",
        box=BoundingBox(x0=10, top=20, x1=180, bottom=40),
    )
    unrelated = row_with_box(
        "unrelated",
        page_index=1,
        text="UNRELATED TRANSACTION",
        box=BoundingBox(x0=10, top=120, x1=150, bottom=140),
        redaction_boxes=(
            BoundingBox(x0=10, top=120, x1=50, bottom=140),
            BoundingBox(x0=100, top=120, x1=150, bottom=140),
        ),
    )
    decision = MatchDecision(
        receipt_id="receipt-1",
        statement_row_ids=(selected.id,),
        status=MatchStatus.ACCEPTED,
        reason="accepted",
    )

    render_composite(
        receipt_path,
        statement_path,
        decision,
        (selected, unrelated),
        output_path,
    )

    output = PdfReader(output_path)
    assert len(output.pages) == 2
    assert output.pages[1].extract_text() in (None, "")

    rendered = pdfium.PdfDocument(output_path)
    try:
        image = rendered[1].render(scale=1).to_pil().convert("RGB")
        assert max(image.getpixel((30, 130))) < 10
        assert min(image.getpixel((75, 130))) > 240
        assert max(image.getpixel((100, 30))) > 10
    finally:
        rendered.close()


def test_reject_unaccepted_match(tmp_path: Path) -> None:
    decision = MatchDecision(
        receipt_id="receipt-1",
        status=MatchStatus.UNMATCHED,
        reason="unmatched",
    )

    with pytest.raises(RenderingError, match="accepted"):
        render_composite(
            tmp_path / "receipt.pdf",
            tmp_path / "statement.pdf",
            decision,
            (),
            tmp_path / "output.pdf",
        )


def row_with_box(
    row_id: str,
    *,
    page_index: int,
    text: str,
    box: BoundingBox,
    redaction_boxes: tuple[BoundingBox, ...] = (),
) -> StatementRow:
    row = make_row(row_id, text, "EUR", "11.42")
    return row.model_copy(
        update={
            "page_index": page_index,
            "source": SourceSpan(
                document_id=row.document_id,
                page_index=page_index,
                text=text,
                box=box,
            ),
            "redaction_boxes": redaction_boxes,
        }
    )

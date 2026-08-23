from pathlib import Path
from typing import cast

import pytest
from pypdf import PdfReader
from pypdf.generic import ArrayObject

from receipts_merger.models import (
    BoundingBox,
    MatchDecision,
    MatchStatus,
)
from receipts_merger.rendering import (
    RenderingError,
    highlight_geometry,
    render_composite,
)
from tests.helpers import write_pdf, write_pdf_pages
from tests.test_matching import make_row


def test_convert_top_left_box_to_pdf_coordinates() -> None:
    box = BoundingBox(x0=10, top=20, x1=110, bottom=40)

    rect, points = highlight_geometry(box, page_height=800)

    assert rect == (10, 760, 110, 780)
    assert [float(value) for value in points] == [10, 780, 110, 780, 10, 760, 110, 760]


def test_render_receipt_with_annotated_statement(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.pdf"
    statement_path = tmp_path / "statement.pdf"
    output_path = tmp_path / "output.pdf"
    write_pdf(receipt_path, ("Receipt",))
    write_pdf_pages(statement_path, (("Statement row",), ("Statement continuation",)))
    row = make_row("row-1", "EXAMPLE TAXI", "EUR", "11.42")
    decision = MatchDecision(
        receipt_id="receipt-1",
        statement_row_ids=(row.id,),
        status=MatchStatus.ACCEPTED,
        reason="accepted",
    )

    render_composite(receipt_path, statement_path, decision, (row,), output_path)

    output = PdfReader(output_path)
    assert len(output.pages) == 3
    annotations = cast(ArrayObject, output.pages[1]["/Annots"])
    annotation = annotations[0].get_object()
    assert annotation["/Subtype"] == "/Highlight"
    assert annotation["/F"] == 4


def test_render_only_relevant_statement_pages(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.pdf"
    statement_path = tmp_path / "statement.pdf"
    output_path = tmp_path / "output.pdf"
    write_pdf(receipt_path, ("Receipt",))
    write_pdf_pages(statement_path, (("First",), ("Second",)))
    row = make_row("row-1", "EXAMPLE TAXI", "EUR", "11.42")
    decision = MatchDecision(
        receipt_id="receipt-1",
        statement_row_ids=(row.id,),
        status=MatchStatus.ACCEPTED,
        reason="accepted",
    )

    render_composite(
        receipt_path,
        statement_path,
        decision,
        (row,),
        output_path,
        full_statement=False,
    )

    assert len(PdfReader(output_path).pages) == 2


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

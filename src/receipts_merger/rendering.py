from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Highlight
from pypdf.generic import ArrayObject, FloatObject

from receipts_merger.models import (
    BoundingBox,
    MatchDecision,
    MatchStatus,
    StatementRow,
)


class RenderingError(ValueError):
    pass


def render_composite(
    receipt_path: Path,
    statement_path: Path,
    decision: MatchDecision,
    rows: tuple[StatementRow, ...],
    output_path: Path,
    *,
    full_statement: bool = True,
) -> None:
    if decision.status is not MatchStatus.ACCEPTED:
        raise RenderingError("only accepted matches can be rendered")

    rows_by_id = {row.id: row for row in rows}
    try:
        selected_rows = tuple(rows_by_id[row_id] for row_id in decision.statement_row_ids)
    except KeyError as error:
        raise RenderingError(f"unknown statement row ID: {error.args[0]}") from error

    statement_reader = PdfReader(statement_path)
    page_indices = (
        tuple(range(len(statement_reader.pages)))
        if full_statement
        else tuple(sorted({row.page_index for row in selected_rows}))
    )
    page_positions = {source_index: position for position, source_index in enumerate(page_indices)}

    writer = PdfWriter()
    writer.append(receipt_path)
    receipt_page_count = len(writer.pages)
    writer.append(statement_reader, pages=list(page_indices))

    for row in selected_rows:
        if row.page_index not in page_positions:
            raise RenderingError(f"statement page is missing: {row.page_index}")
        output_page_index = receipt_page_count + page_positions[row.page_index]
        page = writer.pages[output_page_index]
        rect, quad_points = highlight_geometry(
            row.source.box,
            page_height=float(page.cropbox.height),
            x_offset=float(page.cropbox.left),
            y_offset=float(page.cropbox.bottom),
        )
        writer.add_annotation(
            page_number=output_page_index,
            annotation=Highlight(
                rect=rect,
                quad_points=quad_points,
                highlight_color="fff176",
                printing=True,
            ),
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    with temporary_path.open("wb") as output_file:
        writer.write(output_file)
    temporary_path.replace(output_path)


def highlight_geometry(
    box: BoundingBox,
    page_height: float,
    x_offset: float = 0,
    y_offset: float = 0,
) -> tuple[tuple[float, float, float, float], ArrayObject]:
    left = x_offset + box.x0
    right = x_offset + box.x1
    bottom = y_offset + page_height - box.bottom
    top = y_offset + page_height - box.top
    rect = (left, bottom, right, top)
    quad_points = ArrayObject(
        [
            FloatObject(left),
            FloatObject(top),
            FloatObject(right),
            FloatObject(top),
            FloatObject(left),
            FloatObject(bottom),
            FloatObject(right),
            FloatObject(bottom),
        ]
    )
    return rect, quad_points

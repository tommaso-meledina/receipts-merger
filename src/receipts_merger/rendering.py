from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter

from receipts_merger.models import (
    BoundingBox,
    MatchDecision,
    MatchStatus,
    StatementRow,
)

RENDER_DPI = 200
ROW_PADDING_POINTS = 2
WORD_PADDING_POINTS = 0.75


class RenderingError(ValueError):
    pass


def render_composite(
    receipt_path: Path,
    statement_path: Path,
    decision: MatchDecision,
    rows: tuple[StatementRow, ...],
    output_path: Path,
) -> None:
    if decision.status is not MatchStatus.ACCEPTED:
        raise RenderingError("only accepted matches can be rendered")

    rows_by_id = {row.id: row for row in rows}
    try:
        selected_rows = tuple(rows_by_id[row_id] for row_id in decision.statement_row_ids)
    except KeyError as error:
        raise RenderingError(f"unknown statement row ID: {error.args[0]}") from error

    page_indices = tuple(sorted({row.page_index for row in selected_rows}))
    selected_ids = {row.id for row in selected_rows}

    writer = PdfWriter()
    writer.append(receipt_path)
    buffers: list[BytesIO] = []
    statement_document = pdfium.PdfDocument(statement_path)
    try:
        for page_index in page_indices:
            if page_index >= len(statement_document):
                raise RenderingError(f"statement page is missing: {page_index}")
            page_rows = tuple(row for row in rows if row.page_index == page_index)
            selected_page_rows = tuple(row for row in page_rows if row.id in selected_ids)
            rasterized = _redact_page(
                statement_document[page_index],
                page_rows,
                selected_page_rows,
            )
            buffer = BytesIO()
            rasterized.save(buffer, format="PDF", resolution=RENDER_DPI)
            buffer.seek(0)
            buffers.append(buffer)
            writer.add_page(PdfReader(buffer).pages[0])
    finally:
        statement_document.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    with temporary_path.open("wb") as output_file:
        writer.write(output_file)
    temporary_path.replace(output_path)


def _redact_page(
    page: pdfium.PdfPage,
    rows: tuple[StatementRow, ...],
    selected_rows: tuple[StatementRow, ...],
) -> Image.Image:
    image = page.render(scale=RENDER_DPI / 72).to_pil().convert("RGB")
    x_scale = image.width / page.get_width()
    y_scale = image.height / page.get_height()
    selected_ids = {row.id for row in selected_rows}

    draw = ImageDraw.Draw(image)
    for row in rows:
        if row.id in selected_ids:
            continue
        boxes = row.redaction_boxes or (row.source.box,)
        for box in boxes:
            draw.rectangle(
                _pixel_box(
                    box,
                    page,
                    x_scale,
                    y_scale,
                    WORD_PADDING_POINTS,
                ),
                fill="black",
            )

    for row in selected_rows:
        highlight_box = _pixel_box(
            row.source.box,
            page,
            x_scale,
            y_scale,
            ROW_PADDING_POINTS,
        )
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle(
            highlight_box,
            fill=(255, 241, 118, 72),
            outline=(255, 193, 7, 255),
            width=max(2, round(x_scale)),
        )
        image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")

    return image


def _pixel_box(
    box: BoundingBox,
    page: pdfium.PdfPage,
    x_scale: float,
    y_scale: float,
    padding: float,
) -> tuple[int, int, int, int]:
    return (
        round(max(0, box.x0 - padding) * x_scale),
        round(max(0, box.top - padding) * y_scale),
        round(min(page.get_width(), box.x1 + padding) * x_scale),
        round(min(page.get_height(), box.bottom + padding) * y_scale),
    )

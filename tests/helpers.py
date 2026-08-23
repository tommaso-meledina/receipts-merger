from pathlib import Path

from fpdf import FPDF

from receipts_merger.models import (
    BoundingBox,
    Document,
    DocumentKind,
    ExtractedDocument,
    ExtractedPage,
    Word,
)


def write_pdf(path: Path, lines: tuple[str, ...]) -> None:
    write_pdf_pages(path, (lines,))


def write_pdf_pages(path: Path, pages: tuple[tuple[str, ...], ...]) -> None:
    pdf = FPDF()
    for lines in pages:
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        for line in lines:
            pdf.cell(0, 8, text=line, new_x="LMARGIN", new_y="NEXT")
    pdf.output(path)


def extracted_document(lines: tuple[str, ...], kind: DocumentKind) -> ExtractedDocument:
    words: list[Word] = []
    for line_index, line in enumerate(lines):
        x = 10.0
        top = 10.0 + line_index * 12
        for text in line.split():
            width = max(len(text) * 5.0, 5.0)
            words.append(
                Word(
                    text=text,
                    box=BoundingBox(x0=x, top=top, x1=x + width, bottom=top + 8),
                )
            )
            x += width + 4

    document = Document(id="a" * 64, path=Path("document.pdf"), kind=kind, page_count=1)
    return ExtractedDocument(
        document=document,
        pages=(ExtractedPage(index=0, width=595, height=842, words=tuple(words)),),
        working_path=document.path,
    )

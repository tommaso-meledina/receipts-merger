import hashlib
import re
from pathlib import Path

import pdfplumber

from receipts_merger.models import Document, DocumentKind, ExtractedDocument

DATE_TOKEN = re.compile(r"\b(?:\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{4}-\d{2}-\d{2})\b")
AMOUNT_TOKEN = re.compile(r"(?:\d{1,3}(?:[.,]\d{3})*|\d+)[.,]\d{2}\b")


class DocumentError(ValueError):
    pass


def discover_pdfs(input_directory: Path) -> tuple[Path, ...]:
    if not input_directory.is_dir():
        raise DocumentError(f"input directory does not exist: {input_directory}")

    paths = tuple(sorted(input_directory.glob("*.pdf"), key=lambda path: path.name.casefold()))
    if not paths:
        raise DocumentError(f"input directory contains no PDF files: {input_directory}")
    return paths


def inventory_document(path: Path) -> Document:
    try:
        with pdfplumber.open(path) as pdf:
            page_count = len(pdf.pages)
    except Exception as error:
        raise DocumentError(f"cannot open PDF: {path}") from error

    return Document(
        id=_sha256(path),
        path=path.resolve(),
        kind=DocumentKind.UNKNOWN,
        page_count=page_count,
    )


def classify_document(extracted: ExtractedDocument) -> DocumentKind:
    text = "\n".join(page.text for page in extracted.pages)
    date_count = len(DATE_TOKEN.findall(text))
    amount_count = len(AMOUNT_TOKEN.findall(text))
    word_count = sum(len(page.words) for page in extracted.pages)

    if extracted.document.page_count > 1 and word_count >= 80:
        return DocumentKind.STATEMENT
    if date_count >= 4 and amount_count >= 4 and word_count >= 60:
        return DocumentKind.STATEMENT
    return DocumentKind.RECEIPT


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as pdf_file:
        while chunk := pdf_file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()

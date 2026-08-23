from pathlib import Path
from typing import Any

import ocrmypdf
import pdfplumber

from receipts_merger.config import OcrConfig
from receipts_merger.documents import classify_document, inventory_document
from receipts_merger.models import (
    BoundingBox,
    Document,
    ExtractedDocument,
    ExtractedPage,
    Word,
)


class ExtractionError(RuntimeError):
    pass


def extract_document(path: Path, work_directory: Path, config: OcrConfig) -> ExtractedDocument:
    document = inventory_document(path)
    extracted = _extract_text(document.path, document)

    if _text_length(extracted) < config.minimum_text_characters:
        ocr_path = work_directory / f"{document.id}.ocr.pdf"
        _run_ocr(document.path, ocr_path, config)
        extracted = _extract_text(ocr_path, document).model_copy(
            update={"working_path": ocr_path, "ocr_applied": True}
        )

    kind = classify_document(extracted)
    return extracted.model_copy(update={"document": document.model_copy(update={"kind": kind})})


def _extract_text(path: Path, document: Document) -> ExtractedDocument:
    try:
        with pdfplumber.open(path) as pdf:
            pages = tuple(_extract_page(index, page) for index, page in enumerate(pdf.pages))
    except Exception as error:
        raise ExtractionError(f"cannot extract text from PDF: {document.path}") from error

    return ExtractedDocument(document=document, pages=pages, working_path=path)


def _extract_page(index: int, page: Any) -> ExtractedPage:
    words = tuple(
        Word(
            text=str(word["text"]),
            box=BoundingBox(
                x0=float(word["x0"]),
                top=float(word["top"]),
                x1=float(word["x1"]),
                bottom=float(word["bottom"]),
            ),
        )
        for word in page.extract_words(keep_blank_chars=False)
        if word["text"].strip()
    )
    return ExtractedPage(
        index=index,
        width=float(page.width),
        height=float(page.height),
        words=words,
    )


def _run_ocr(input_path: Path, output_path: Path, config: OcrConfig) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.unlink(missing_ok=True)

    try:
        exit_code = ocrmypdf.ocr(
            input_path,
            output_path,
            language=config.languages,
            output_type="pdf",
            deskew=True,
            skip_text=True,
            progress_bar=False,
        )
    except Exception as error:
        raise ExtractionError(f"OCR failed for PDF: {input_path}") from error

    if exit_code != ocrmypdf.ExitCode.ok:
        raise ExtractionError(f"OCR failed with exit code {exit_code}: {input_path}")


def _text_length(extracted: ExtractedDocument) -> int:
    return sum(len(page.text) for page in extracted.pages)

import re
from datetime import date
from pathlib import Path

from receipts_merger.config import ParsingConfig
from receipts_merger.models import ExtractedDocument, Money, Receipt, SourceSpan
from receipts_merger.parsers.common import (
    TextLine,
    find_money,
    infer_currency,
    lines_from_page,
    parse_date,
)

TOTAL_LABEL = re.compile(
    r"\b(?:amount due|amount paid|charged|grand total|total|totale|gesamt)\b",
    re.IGNORECASE,
)
NON_MERCHANT = re.compile(
    r"\b(?:invoice|receipt|order|tax|date|total|amount|payment|welcome|percorso)\b",
    re.IGNORECASE,
)
MERCHANT_FIELD = re.compile(r"^(?:location|merchant|store)\s*[:#-]\s*(.+)$", re.IGNORECASE)
CARD_SUFFIX = re.compile(
    r"(?:ending(?:\s+in)?|last\s*4|[*xX]{2,})\s*[:#-]?\s*(\d{4})",
    re.IGNORECASE,
)
FILENAME_DATE = re.compile(r"^(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})(?=\D|$)")


def parse_receipt(
    extracted: ExtractedDocument,
    config: ParsingConfig,
    default_currency: str | None = None,
) -> Receipt:
    page_lines = tuple(
        (page.index, line)
        for page in extracted.pages
        for line in lines_from_page(page)
        if line.text.strip()
    )
    full_text = "\n".join(line.text for _, line in page_lines)
    currency = infer_currency(full_text) or default_currency

    merchant_field_match = next(
        (
            (page_index, line, field.group(1).strip())
            for page_index, line in page_lines
            if (field := MERCHANT_FIELD.match(line.text))
            and _is_merchant_candidate(line, field.group(1))
        ),
        None,
    )
    merchant_match = next(
        ((page_index, line) for page_index, line in page_lines if _is_merchant_candidate(line)),
        None,
    )
    if merchant_field_match:
        merchant_source = merchant_field_match[:2]
        merchant = merchant_field_match[2]
    else:
        merchant_source = merchant_match
        merchant = merchant_match[1].text if merchant_match else None
    filename_hint = _filename_hint(extracted.document.path)
    text_date_match = next(
        (
            (page_index, line, parsed)
            for page_index, line in page_lines
            if (parsed := parse_date(line.text, config.day_first)) is not None
        ),
        None,
    )
    total_match = _find_total(page_lines, currency)
    purchased_on = _filename_date(extracted.document.path) or (
        text_date_match[2] if text_date_match else None
    )

    sources = tuple(
        _source(extracted, page_index, line)
        for page_index, line in _unique_lines(
            merchant_source,
            text_date_match[:2] if text_date_match else None,
            total_match[:2] if total_match else None,
        )
    )
    return Receipt(
        document_id=extracted.document.id,
        merchant=merchant,
        merchant_hint=filename_hint,
        purchased_on=purchased_on,
        total=total_match[2] if total_match else None,
        card_suffix=card_match.group(1) if (card_match := CARD_SUFFIX.search(full_text)) else None,
        sources=sources,
    )


def _filename_date(path: Path) -> date | None:
    match = FILENAME_DATE.match(path.stem)
    if not match:
        return None
    try:
        return date(*(int(match[name]) for name in ("year", "month", "day")))
    except ValueError:
        return None


def _filename_hint(path: Path) -> str | None:
    match = FILENAME_DATE.match(path.stem)
    if not match:
        return None
    hint = re.sub(r"[_-]+", " ", path.stem[match.end() :]).strip()
    return hint or None


def _find_total(
    page_lines: tuple[tuple[int, TextLine], ...], currency: str | None
) -> tuple[int, TextLine, Money] | None:
    candidates = [
        (page_index, line, money.money)
        for page_index, line in page_lines
        for money in find_money(line.text, currency)
    ]
    labelled = [candidate for candidate in candidates if TOTAL_LABEL.search(candidate[1].text)]
    pool = labelled or candidates
    return max(pool, key=lambda candidate: candidate[2].amount) if pool else None


def _is_merchant_candidate(line: TextLine, text: str | None = None) -> bool:
    text = text or line.text
    return (
        len(text) <= 120
        and len(re.findall(r"[^\W\d_]", text, re.UNICODE)) >= 3
        and not NON_MERCHANT.search(text)
        and parse_date(text) is None
    )


def _source(extracted: ExtractedDocument, page_index: int, line: TextLine) -> SourceSpan:
    return SourceSpan(
        document_id=extracted.document.id,
        page_index=page_index,
        text=line.text,
        box=line.box,
    )


def _unique_lines(
    *matches: tuple[int, TextLine] | None,
) -> tuple[tuple[int, TextLine], ...]:
    unique: dict[tuple[int, str], tuple[int, TextLine]] = {}
    for match in matches:
        if match is not None:
            unique[(match[0], match[1].text)] = match
    return tuple(unique.values())

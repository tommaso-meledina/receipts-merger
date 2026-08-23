import re

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
    r"\b(?:invoice|receipt|order|tax|date|total|amount|payment)\b",
    re.IGNORECASE,
)
CARD_SUFFIX = re.compile(
    r"(?:ending(?:\s+in)?|last\s*4|[*xX]{2,})\s*[:#-]?\s*(\d{4})",
    re.IGNORECASE,
)


def parse_receipt(extracted: ExtractedDocument, config: ParsingConfig) -> Receipt:
    page_lines = tuple(
        (page.index, line)
        for page in extracted.pages
        for line in lines_from_page(page)
        if line.text.strip()
    )
    full_text = "\n".join(line.text for _, line in page_lines)
    currency = infer_currency(full_text)

    merchant_match = next(
        ((page_index, line) for page_index, line in page_lines if _is_merchant_candidate(line)),
        None,
    )
    date_match = next(
        (
            (page_index, line, parsed)
            for page_index, line in page_lines
            if (parsed := parse_date(line.text, config.day_first)) is not None
        ),
        None,
    )
    total_match = _find_total(page_lines, currency)

    sources = tuple(
        _source(extracted, page_index, line)
        for page_index, line in _unique_lines(
            merchant_match,
            date_match[:2] if date_match else None,
            total_match[:2] if total_match else None,
        )
    )
    return Receipt(
        document_id=extracted.document.id,
        merchant=merchant_match[1].text if merchant_match else None,
        purchased_on=date_match[2] if date_match else None,
        total=total_match[2] if total_match else None,
        card_suffix=card_match.group(1) if (card_match := CARD_SUFFIX.search(full_text)) else None,
        sources=sources,
    )


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


def _is_merchant_candidate(line: TextLine) -> bool:
    return (
        len(line.text) <= 120
        and len(re.findall(r"[^\W\d_]", line.text, re.UNICODE)) >= 3
        and not NON_MERCHANT.search(line.text)
        and parse_date(line.text) is None
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

import hashlib

from receipts_merger.config import ParsingConfig
from receipts_merger.models import ExtractedDocument, SourceSpan, StatementRow
from receipts_merger.parsers.common import (
    TextLine,
    find_date,
    find_money,
    infer_currency,
    lines_from_page,
)


def parse_statement(
    extracted: ExtractedDocument, config: ParsingConfig
) -> tuple[StatementRow, ...]:
    rows: list[StatementRow] = []
    for page in extracted.pages:
        lines = lines_from_page(page)
        for line_index, line in enumerate(lines):
            date_match = find_date(line.text, config.day_first)
            money_matches = find_money(line.text, config.default_statement_currency)
            if date_match is None or date_match.start > 4 or not money_matches:
                continue

            following_date = find_date(line.text[date_match.end :], config.day_first)
            if following_date and following_date.start <= 3:
                description_start = date_match.end + following_date.end
                posted_on = following_date.value
            else:
                description_start = date_match.end
                posted_on = None
            description = line.text[description_start : money_matches[0].start].strip(
                " -|\N{EN DASH}\N{EM DASH}"
            )
            if not description:
                continue

            source = SourceSpan(
                document_id=extracted.document.id,
                page_index=page.index,
                text=line.text,
                box=line.box,
            )
            billed_amount = money_matches[-1].money
            original_amount = money_matches[0].money if len(money_matches) > 1 else None
            if original_amount and (
                original_currency := _following_currency(
                    lines[line_index + 1 : line_index + 3],
                    config.default_statement_currency,
                )
            ):
                original_amount = original_amount.model_copy(update={"currency": original_currency})
            rows.append(
                StatementRow(
                    id=_row_id(extracted.document.id, page.index, line.box.top, line.text),
                    document_id=extracted.document.id,
                    page_index=page.index,
                    transacted_on=date_match.value,
                    posted_on=posted_on,
                    description=description,
                    original_amount=original_amount,
                    billed_amount=billed_amount,
                    source=source,
                )
            )
    return tuple(rows)


def _following_currency(
    lines: tuple[TextLine, ...],
    default_currency: str,
) -> str | None:
    for line in lines:
        currency = infer_currency(line.text)
        if currency and currency != default_currency:
            return currency
        if find_date(line.text):
            break
    return None


def _row_id(document_id: str, page_index: int, top: float, text: str) -> str:
    value = f"{document_id}:{page_index}:{top:.3f}:{text}".encode()
    return hashlib.sha256(value).hexdigest()

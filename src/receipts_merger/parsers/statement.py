import hashlib

from receipts_merger.config import ParsingConfig
from receipts_merger.models import ExtractedDocument, SourceSpan, StatementRow
from receipts_merger.parsers.common import find_date, find_money, lines_from_page


def parse_statement(
    extracted: ExtractedDocument, config: ParsingConfig
) -> tuple[StatementRow, ...]:
    rows: list[StatementRow] = []
    for page in extracted.pages:
        for line in lines_from_page(page):
            date_match = find_date(line.text, config.day_first)
            money_matches = find_money(line.text, config.default_statement_currency)
            if date_match is None or date_match.start > 4 or not money_matches:
                continue

            description = line.text[date_match.end : money_matches[0].start].strip(
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
            rows.append(
                StatementRow(
                    id=_row_id(extracted.document.id, page.index, line.box.top, line.text),
                    document_id=extracted.document.id,
                    page_index=page.index,
                    transacted_on=date_match.value,
                    description=description,
                    original_amount=original_amount,
                    billed_amount=billed_amount,
                    source=source,
                )
            )
    return tuple(rows)


def _row_id(document_id: str, page_index: int, top: float, text: str) -> str:
    value = f"{document_id}:{page_index}:{top:.3f}:{text}".encode()
    return hashlib.sha256(value).hexdigest()

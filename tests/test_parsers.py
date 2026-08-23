from datetime import date
from decimal import Decimal

from receipts_merger.config import ParsingConfig
from receipts_merger.models import DocumentKind
from receipts_merger.parsers import parse_receipt, parse_statement
from receipts_merger.parsers.common import find_money, parse_date
from tests.helpers import extracted_document


def test_parse_localized_money() -> None:
    european = find_money("Total EUR 1.234,56")
    american = find_money("Total USD 1,234.56")

    assert european[0].money.amount == Decimal("1234.56")
    assert american[0].money.amount == Decimal("1234.56")


def test_parse_date_order() -> None:
    assert parse_date("06/07/2026", day_first=True) == date(2026, 7, 6)
    assert parse_date("06/07/2026", day_first=False) == date(2026, 6, 7)


def test_parse_receipt_fields() -> None:
    extracted = extracted_document(
        ("Example Taxi", "Date 16/06/2026", "Total USD 12.34"),
        DocumentKind.RECEIPT,
    )

    receipt = parse_receipt(extracted, ParsingConfig())

    assert receipt.merchant == "Example Taxi"
    assert receipt.purchased_on == date(2026, 6, 16)
    assert receipt.total is not None
    assert receipt.total.amount == Decimal("12.34")
    assert receipt.total.currency == "USD"
    assert len(receipt.sources) == 3


def test_parse_statement_row() -> None:
    extracted = extracted_document(
        ("Transactions", "16/06/2026 EXAMPLE TAXI USD 12.34 EUR 11.42"),
        DocumentKind.STATEMENT,
    )

    rows = parse_statement(extracted, ParsingConfig())

    assert len(rows) == 1
    assert rows[0].description == "EXAMPLE TAXI"
    assert rows[0].transacted_on == date(2026, 6, 16)
    assert rows[0].original_amount is not None
    assert rows[0].original_amount.currency == "USD"
    assert rows[0].billed_amount.amount == Decimal("11.42")
    assert rows[0].billed_amount.currency == "EUR"

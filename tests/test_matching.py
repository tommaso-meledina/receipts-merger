from datetime import date
from decimal import Decimal

from receipts_merger.config import MatchingConfig
from receipts_merger.matching import match_receipts, normalize_merchant
from receipts_merger.models import (
    BoundingBox,
    MatchStatus,
    Money,
    Receipt,
    SourceSpan,
    StatementRow,
)


def test_normalize_merchant() -> None:
    assert normalize_merchant("The Café, GmbH") == "cafe"


def test_accept_exact_original_amount_match() -> None:
    receipt = make_receipt("receipt-1", "Example Taxi", "USD", "12.34")
    row = make_row("row-1", "EXAMPLE TAXI", "EUR", "11.42", original=("USD", "12.34"))

    result = match_receipts((receipt,), (row,), MatchingConfig())

    assert result.decisions[0].status is MatchStatus.ACCEPTED
    assert result.decisions[0].statement_row_ids == ("row-1",)
    assert result.decisions[0].score is not None
    assert result.decisions[0].score.total == 95


def test_exclude_row_outside_date_window() -> None:
    receipt = make_receipt("receipt-1", "Example Taxi", "EUR", "11.42")
    row = make_row(
        "row-1",
        "EXAMPLE TAXI",
        "EUR",
        "11.42",
        transacted_on=date(2026, 7, 1),
    )

    result = match_receipts((receipt,), (row,), MatchingConfig())

    assert result.decisions[0].status is MatchStatus.UNMATCHED
    assert result.candidates == ()


def test_abstain_when_runner_up_is_too_close() -> None:
    receipt = make_receipt("receipt-1", "Example Taxi", "EUR", "11.42")
    rows = (
        make_row("row-1", "EXAMPLE TAXI", "EUR", "11.42"),
        make_row("row-2", "EXAMPLE TAXI UK", "EUR", "11.42"),
    )

    result = match_receipts((receipt,), rows, MatchingConfig())

    assert result.decisions[0].status is MatchStatus.AMBIGUOUS
    assert "runner-up" in result.decisions[0].reason


def test_do_not_reuse_statement_row() -> None:
    receipts = (
        make_receipt("receipt-1", "Example Taxi", "EUR", "11.42"),
        make_receipt("receipt-2", "Example Taxi", "EUR", "11.42"),
    )
    row = make_row("row-1", "EXAMPLE TAXI", "EUR", "11.42")

    result = match_receipts(receipts, (row,), MatchingConfig())

    assert {decision.status for decision in result.decisions} == {MatchStatus.AMBIGUOUS}


def make_receipt(
    receipt_id: str,
    merchant: str,
    currency: str,
    amount: str,
) -> Receipt:
    return Receipt(
        document_id=receipt_id,
        merchant=merchant,
        purchased_on=date(2026, 6, 16),
        total=Money(currency=currency, amount=Decimal(amount)),
    )


def make_row(
    row_id: str,
    description: str,
    currency: str,
    amount: str,
    *,
    original: tuple[str, str] | None = None,
    transacted_on: date = date(2026, 6, 16),
) -> StatementRow:
    source = SourceSpan(
        document_id="statement",
        page_index=0,
        text=description,
        box=BoundingBox(x0=10, top=10, x1=100, bottom=20),
    )
    return StatementRow(
        id=row_id,
        document_id="statement",
        page_index=0,
        transacted_on=transacted_on,
        description=description,
        original_amount=(
            Money(currency=original[0], amount=Decimal(original[1])) if original else None
        ),
        billed_amount=Money(currency=currency, amount=Decimal(amount)),
        source=source,
    )

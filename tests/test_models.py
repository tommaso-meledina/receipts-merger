from decimal import Decimal

import pytest
from pydantic import ValidationError

from receipts_merger.models import Money, ScoreBreakdown


def test_money_requires_iso_currency() -> None:
    money = Money(amount=Decimal("12.34"), currency="EUR")

    assert money.amount == Decimal("12.34")


def test_money_rejects_non_iso_currency() -> None:
    with pytest.raises(ValidationError):
        Money(amount=Decimal("12.34"), currency="€")


def test_score_total() -> None:
    score = ScoreBreakdown(amount=50, date=20, merchant=25, card=5)

    assert score.total == 100

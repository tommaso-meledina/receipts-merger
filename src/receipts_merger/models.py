from datetime import date
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(frozen=True)


class DocumentKind(StrEnum):
    RECEIPT = "receipt"
    STATEMENT = "statement"
    UNKNOWN = "unknown"


class MatchStatus(StrEnum):
    ACCEPTED = "accepted"
    AMBIGUOUS = "ambiguous"
    UNMATCHED = "unmatched"


class BoundingBox(Model):
    x0: float = Field(ge=0)
    top: float = Field(ge=0)
    x1: float = Field(ge=0)
    bottom: float = Field(ge=0)


class SourceSpan(Model):
    document_id: str
    page_index: int = Field(ge=0)
    text: str
    box: BoundingBox


class Money(Model):
    amount: Decimal
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class Document(Model):
    id: str
    path: Path
    kind: DocumentKind
    page_count: int = Field(gt=0)


class Receipt(Model):
    document_id: str
    merchant: str | None = None
    purchased_on: date | None = None
    total: Money | None = None
    card_suffix: str | None = Field(default=None, pattern=r"^\d{4}$")
    sources: tuple[SourceSpan, ...] = ()


class StatementRow(Model):
    id: str
    document_id: str
    page_index: int = Field(ge=0)
    transacted_on: date | None = None
    posted_on: date | None = None
    description: str
    original_amount: Money | None = None
    billed_amount: Money
    source: SourceSpan


class ScoreBreakdown(Model):
    amount: int = Field(ge=0)
    date: int = Field(ge=0)
    merchant: int = Field(ge=0)
    card: int = Field(ge=0)

    @property
    def total(self) -> int:
        return self.amount + self.date + self.merchant + self.card


class MatchDecision(Model):
    receipt_id: str
    statement_row_ids: tuple[str, ...] = ()
    status: MatchStatus
    score: ScoreBreakdown | None = None
    reason: str

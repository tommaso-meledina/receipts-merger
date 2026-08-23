from datetime import date
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


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

    @model_validator(mode="after")
    def validate_edges(self) -> Self:
        if self.x1 < self.x0 or self.bottom < self.top:
            raise ValueError("box edges are inverted")
        return self


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


class Word(Model):
    text: str
    box: BoundingBox


class ExtractedPage(Model):
    index: int = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    words: tuple[Word, ...]

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)


class ExtractedDocument(Model):
    document: Document
    pages: tuple[ExtractedPage, ...]
    working_path: Path
    ocr_applied: bool = False


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
    redaction_boxes: tuple[BoundingBox, ...] = ()


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


class CandidateMatch(Model):
    receipt_id: str
    statement_row_ids: tuple[str, ...]
    score: ScoreBreakdown


class MatchResult(Model):
    candidates: tuple[CandidateMatch, ...]
    decisions: tuple[MatchDecision, ...]


class MatchOverride(Model):
    receipt_id: str
    statement_row_ids: tuple[str, ...] = ()
    status: MatchStatus
    reason: str


class RunManifest(Model):
    schema_version: int = 1
    documents: tuple[Document, ...]
    receipts: tuple[Receipt, ...]
    statement_rows: tuple[StatementRow, ...]
    candidates: tuple[CandidateMatch, ...]
    decisions: tuple[MatchDecision, ...]

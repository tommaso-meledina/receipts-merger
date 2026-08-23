import re
import unicodedata
from collections import defaultdict
from datetime import date
from decimal import Decimal

from rapidfuzz.fuzz import token_set_ratio

from receipts_merger.config import MatchingConfig
from receipts_merger.models import (
    CandidateMatch,
    MatchDecision,
    MatchResult,
    MatchStatus,
    Money,
    Receipt,
    ScoreBreakdown,
    StatementRow,
)

MERCHANT_NOISE = re.compile(r"\b(?:inc|incorporated|ltd|limited|llc|gmbh|sarl|sa|spa|plc|the)\b")
NON_ALPHANUMERIC = re.compile(r"[^\w\s]")


def match_receipts(
    receipts: tuple[Receipt, ...],
    rows: tuple[StatementRow, ...],
    config: MatchingConfig,
) -> MatchResult:
    ranked = {receipt.document_id: rank_candidates(receipt, rows, config) for receipt in receipts}
    candidates = tuple(
        candidate for receipt_id in sorted(ranked) for candidate in ranked[receipt_id]
    )
    provisional = {
        receipt.document_id: _decide(receipt, ranked[receipt.document_id], config)
        for receipt in receipts
    }
    decisions = _resolve_conflicts(provisional, config)
    return MatchResult(candidates=candidates, decisions=decisions)


def rank_candidates(
    receipt: Receipt,
    rows: tuple[StatementRow, ...],
    config: MatchingConfig,
) -> tuple[CandidateMatch, ...]:
    if receipt.total is None or receipt.purchased_on is None:
        return ()

    candidates = [
        candidate for row in rows if (candidate := _score(receipt, row, config)) is not None
    ]
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (-candidate.score.total, candidate.statement_row_ids),
        )
    )


def normalize_merchant(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    normalized = NON_ALPHANUMERIC.sub(" ", normalized)
    normalized = MERCHANT_NOISE.sub(" ", normalized)
    return " ".join(normalized.split())


def _score(
    receipt: Receipt,
    row: StatementRow,
    config: MatchingConfig,
) -> CandidateMatch | None:
    if receipt.total is None or receipt.purchased_on is None:
        return None
    amount_score = _amount_score(receipt.total, row)
    row_date = row.transacted_on or row.posted_on
    date_score = _date_score(receipt.purchased_on, row_date, config)
    if amount_score is None or date_score is None:
        return None

    merchant_score = _merchant_score(receipt.merchant, row.description)
    card_score = 5 if receipt.card_suffix and receipt.card_suffix in row.description else 0
    return CandidateMatch(
        receipt_id=receipt.document_id,
        statement_row_ids=(row.id,),
        score=ScoreBreakdown(
            amount=amount_score,
            date=date_score,
            merchant=merchant_score,
            card=card_score,
        ),
    )


def _amount_score(receipt_total: Money, row: StatementRow) -> int | None:
    values = tuple(money for money in (row.original_amount, row.billed_amount) if money is not None)
    scores = [
        score
        for value in values
        if receipt_total.currency == value.currency
        if (score := _same_currency_amount_score(receipt_total, value)) is not None
    ]
    return max(scores, default=None)


def _same_currency_amount_score(left: Money, right: Money) -> int | None:
    difference = abs(left.amount - right.amount)
    if difference == Decimal():
        return 55
    if difference <= Decimal("0.02"):
        return 50
    return None


def _date_score(
    receipt_date: date,
    statement_date: date | None,
    config: MatchingConfig,
) -> int | None:
    if statement_date is None:
        return None
    difference = (statement_date - receipt_date).days
    if difference < -config.days_before or difference > config.days_after:
        return None
    return max(5, 25 - abs(difference) * 2)


def _merchant_score(receipt_merchant: str | None, description: str) -> int:
    if not receipt_merchant:
        return 0
    similarity = token_set_ratio(
        normalize_merchant(receipt_merchant),
        normalize_merchant(description),
    )
    return round(similarity * 15 / 100)


def _decide(
    receipt: Receipt,
    candidates: tuple[CandidateMatch, ...],
    config: MatchingConfig,
) -> MatchDecision:
    if receipt.total is None or receipt.purchased_on is None or not receipt.merchant:
        return MatchDecision(
            receipt_id=receipt.document_id,
            status=MatchStatus.UNMATCHED,
            reason="receipt is missing merchant, date, or total",
        )
    if not candidates:
        return MatchDecision(
            receipt_id=receipt.document_id,
            status=MatchStatus.UNMATCHED,
            reason="no statement row passed the amount and date constraints",
        )

    best = candidates[0]
    if best.score.total < config.acceptance_score:
        return MatchDecision(
            receipt_id=receipt.document_id,
            statement_row_ids=best.statement_row_ids,
            status=MatchStatus.AMBIGUOUS,
            score=best.score,
            reason="best candidate is below the acceptance score",
        )
    if len(candidates) > 1 and best.score.total - candidates[1].score.total < config.minimum_margin:
        return MatchDecision(
            receipt_id=receipt.document_id,
            statement_row_ids=best.statement_row_ids,
            status=MatchStatus.AMBIGUOUS,
            score=best.score,
            reason="best candidate is too close to the runner-up",
        )
    return MatchDecision(
        receipt_id=receipt.document_id,
        statement_row_ids=best.statement_row_ids,
        status=MatchStatus.ACCEPTED,
        score=best.score,
        reason="candidate passed the score and margin thresholds",
    )


def _resolve_conflicts(
    provisional: dict[str, MatchDecision],
    config: MatchingConfig,
) -> tuple[MatchDecision, ...]:
    claims: defaultdict[str, list[MatchDecision]] = defaultdict(list)
    for decision in provisional.values():
        if decision.status is MatchStatus.ACCEPTED:
            for row_id in decision.statement_row_ids:
                claims[row_id].append(decision)

    conflicted: set[str] = set()
    for decisions in claims.values():
        ordered = sorted(decisions, key=lambda item: -(item.score.total if item.score else 0))
        if len(ordered) < 2:
            continue
        best_score = ordered[0].score.total if ordered[0].score else 0
        second_score = ordered[1].score.total if ordered[1].score else 0
        if best_score - second_score < config.minimum_margin:
            conflicted.update(decision.receipt_id for decision in ordered)
        else:
            conflicted.update(decision.receipt_id for decision in ordered[1:])

    resolved = [
        decision.model_copy(
            update={
                "status": MatchStatus.AMBIGUOUS,
                "reason": "statement row is also claimed by another receipt",
            }
        )
        if receipt_id in conflicted
        else decision
        for receipt_id, decision in provisional.items()
    ]
    return tuple(sorted(resolved, key=lambda decision: decision.receipt_id))

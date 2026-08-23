from pathlib import Path

from pydantic import TypeAdapter

from receipts_merger.models import (
    MatchDecision,
    MatchOverride,
    MatchResult,
    MatchStatus,
    StatementRow,
)

OVERRIDES = TypeAdapter(tuple[MatchOverride, ...])


class OverrideError(ValueError):
    pass


def read_overrides(path: Path) -> tuple[MatchOverride, ...]:
    return OVERRIDES.validate_json(path.read_text())


def apply_overrides(
    result: MatchResult,
    overrides: tuple[MatchOverride, ...],
    rows: tuple[StatementRow, ...],
) -> MatchResult:
    known_rows = {row.id for row in rows}
    decisions = {decision.receipt_id: decision for decision in result.decisions}

    for override in overrides:
        if override.receipt_id not in decisions:
            raise OverrideError(f"unknown receipt ID: {override.receipt_id}")
        if override.status is MatchStatus.ACCEPTED and not override.statement_row_ids:
            raise OverrideError("accepted override requires at least one statement row")
        if unknown := set(override.statement_row_ids) - known_rows:
            raise OverrideError(f"unknown statement row ID: {min(unknown)}")

        decisions[override.receipt_id] = MatchDecision(
            receipt_id=override.receipt_id,
            statement_row_ids=override.statement_row_ids,
            status=override.status,
            reason=override.reason,
        )

    claimed_rows: dict[str, str] = {}
    for decision in decisions.values():
        if decision.status is not MatchStatus.ACCEPTED:
            continue
        for row_id in decision.statement_row_ids:
            if owner := claimed_rows.get(row_id):
                raise OverrideError(
                    f"statement row is claimed by both {owner} and {decision.receipt_id}"
                )
            claimed_rows[row_id] = decision.receipt_id

    return result.model_copy(
        update={
            "decisions": tuple(sorted(decisions.values(), key=lambda decision: decision.receipt_id))
        }
    )

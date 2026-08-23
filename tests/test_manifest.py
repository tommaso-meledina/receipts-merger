from pathlib import Path

import pytest

from receipts_merger.config import MatchingConfig
from receipts_merger.manifest import read_manifest, write_manifest
from receipts_merger.matching import match_receipts
from receipts_merger.models import (
    MatchOverride,
    MatchStatus,
    RunManifest,
)
from receipts_merger.review import OverrideError, apply_overrides
from tests.test_matching import make_receipt, make_row


def test_manifest_round_trip(tmp_path: Path) -> None:
    manifest = RunManifest(
        documents=(),
        receipts=(),
        statement_rows=(),
        candidates=(),
        decisions=(),
    )
    path = tmp_path / "manifest.json"

    write_manifest(manifest, path)

    assert read_manifest(path) == manifest
    assert not (tmp_path / "manifest.json.tmp").exists()


def test_apply_override() -> None:
    receipt = make_receipt("receipt-1", "Example Taxi", "EUR", "11.42")
    row = make_row("row-1", "OTHER MERCHANT", "EUR", "11.42")
    result = match_receipts((receipt,), (row,), MatchingConfig())
    override = MatchOverride(
        receipt_id=receipt.document_id,
        statement_row_ids=(row.id,),
        status=MatchStatus.ACCEPTED,
        reason="reviewed manually",
    )

    reviewed = apply_overrides(result, (override,), (row,))

    assert reviewed.decisions[0].status is MatchStatus.ACCEPTED
    assert reviewed.decisions[0].reason == "reviewed manually"


def test_reject_unknown_override_row() -> None:
    receipt = make_receipt("receipt-1", "Example Taxi", "EUR", "11.42")
    result = match_receipts((receipt,), (), MatchingConfig())
    override = MatchOverride(
        receipt_id=receipt.document_id,
        statement_row_ids=("missing",),
        status=MatchStatus.ACCEPTED,
        reason="invalid",
    )

    with pytest.raises(OverrideError, match="unknown statement row"):
        apply_overrides(result, (override,), ())

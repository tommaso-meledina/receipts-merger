from pathlib import Path

import pytest
from pydantic import ValidationError

from receipts_merger.config import AppConfig


def test_default_config() -> None:
    config = AppConfig()

    assert config.ocr.languages == ("eng",)
    assert config.matching.acceptance_score == 80


def test_load_config(tmp_path: Path) -> None:
    path = tmp_path / "receipts-merger.toml"
    path.write_text(
        """
[ocr]
languages = ["eng", "deu"]

[matching]
days_after = 7
""".strip()
    )

    config = AppConfig.from_toml(path)

    assert config.ocr.languages == ("eng", "deu")
    assert config.matching.days_after == 7


def test_reject_invalid_config() -> None:
    with pytest.raises(ValidationError):
        AppConfig.model_validate({"matching": {"acceptance_score": 101}})

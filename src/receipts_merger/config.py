from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field


class OcrConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    languages: tuple[str, ...] = ("eng",)
    minimum_text_characters: int = Field(default=40, ge=0)


class MatchingConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    days_before: int = Field(default=3, ge=0)
    days_after: int = Field(default=10, ge=0)
    acceptance_score: int = Field(default=80, ge=0, le=100)
    minimum_margin: int = Field(default=10, ge=0, le=100)


class ParsingConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    day_first: bool = True
    default_statement_currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")


class AppConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    ocr: OcrConfig = OcrConfig()
    parsing: ParsingConfig = ParsingConfig()
    matching: MatchingConfig = MatchingConfig()

    @classmethod
    def from_toml(cls, path: Path) -> Self:
        import tomllib

        with path.open("rb") as config_file:
            return cls.model_validate(tomllib.load(config_file))

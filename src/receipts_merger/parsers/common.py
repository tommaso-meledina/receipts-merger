import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from receipts_merger.models import BoundingBox, ExtractedPage, Money, Word

CURRENCIES = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "CAD": "CAD",
    "CHF": "CHF",
    "EUR": "EUR",
    "GBP": "GBP",
    "JPY": "JPY",
    "USD": "USD",
}
CURRENCY_PATTERN = "|".join(re.escape(value) for value in CURRENCIES)
AMOUNT_PATTERN = re.compile(
    rf"(?<!\w)(?P<prefix>{CURRENCY_PATTERN})?\s*"
    r"(?P<number>-?\d[\d.,']*[.,]\d{2})"
    rf"(?:\s*(?P<suffix>{CURRENCY_PATTERN}))?(?!\w)",
    re.IGNORECASE,
)
ISO_DATE_PATTERN = re.compile(r"\b(?P<year>\d{4})[-/](?P<month>\d{1,2})[-/](?P<day>\d{1,2})\b")
LOCAL_DATE_PATTERN = re.compile(r"\b(?P<first>\d{1,2})[/-](?P<second>\d{1,2})[/-](?P<year>\d{4})\b")


@dataclass(frozen=True, slots=True)
class TextLine:
    text: str
    words: tuple[Word, ...]
    box: BoundingBox


@dataclass(frozen=True, slots=True)
class MoneyMatch:
    money: Money
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class DateMatch:
    value: date
    start: int
    end: int


def lines_from_page(page: ExtractedPage, tolerance: float = 3.0) -> tuple[TextLine, ...]:
    grouped: list[list[Word]] = []
    for word in sorted(page.words, key=lambda item: (item.box.top, item.box.x0)):
        if not grouped or abs(grouped[-1][0].box.top - word.box.top) > tolerance:
            grouped.append([word])
        else:
            grouped[-1].append(word)

    return tuple(_make_line(words) for words in grouped)


def parse_date(text: str, day_first: bool = True) -> date | None:
    match = find_date(text, day_first)
    return match.value if match else None


def find_date(text: str, day_first: bool = True) -> DateMatch | None:
    if match := ISO_DATE_PATTERN.search(text):
        values = match.groupdict()
        value = _date(values["year"], values["month"], values["day"])
    elif match := LOCAL_DATE_PATTERN.search(text):
        values = match.groupdict()
        day = values["first"] if day_first else values["second"]
        month = values["second"] if day_first else values["first"]
        value = _date(values["year"], month, day)
    else:
        return None
    return DateMatch(value, *match.span()) if value else None


def find_money(text: str, default_currency: str | None = None) -> tuple[MoneyMatch, ...]:
    matches: list[MoneyMatch] = []
    for match in AMOUNT_PATTERN.finditer(text):
        currency_token = match.group("prefix") or match.group("suffix")
        currency = _currency(currency_token) if currency_token else default_currency
        if currency is None:
            continue
        try:
            amount = _decimal(match.group("number"))
        except InvalidOperation:
            continue
        matches.append(MoneyMatch(Money(amount=amount, currency=currency), *match.span()))
    return tuple(matches)


def infer_currency(text: str) -> str | None:
    upper_text = text.upper()
    for token, currency in CURRENCIES.items():
        if token in text or token in upper_text:
            return currency
    return None


def _make_line(words: list[Word]) -> TextLine:
    ordered = tuple(sorted(words, key=lambda word: word.box.x0))
    return TextLine(
        text=" ".join(word.text for word in ordered),
        words=ordered,
        box=BoundingBox(
            x0=min(word.box.x0 for word in ordered),
            top=min(word.box.top for word in ordered),
            x1=max(word.box.x1 for word in ordered),
            bottom=max(word.box.bottom for word in ordered),
        ),
    )


def _currency(token: str) -> str:
    return CURRENCIES[token.upper() if token.isalpha() else token]


def _decimal(value: str) -> Decimal:
    value = value.replace("'", "")
    if "," in value and "." in value:
        decimal_separator = "," if value.rfind(",") > value.rfind(".") else "."
        thousands_separator = "." if decimal_separator == "," else ","
        value = value.replace(thousands_separator, "").replace(decimal_separator, ".")
    elif "," in value:
        value = value.replace(",", ".")
    return Decimal(value)


def _date(year: str, month: str, day: str) -> date | None:
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None

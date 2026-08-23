# Receipts Merger

## What's Receipts Merger?

Receipts Merger is a local CLI that matches scanned paper receipts to credit-card statement
entries. It outputs a complete reimbursement-ready collection using the original receipt filenames.
Foreign-currency matches are enriched with the relevant statement page, while all other receipts
are copied unchanged.

Matching is deterministic and auditable. Amount, currency, date, merchant, and optional card
details contribute to a fixed score; weak or competing matches are left for review instead of
being guessed.

```bash
uv run receipts-merger run ./receipts \
  --statement ./receipts/statement.pdf \
  --output ./merged
```

All extraction, OCR, matching, and PDF generation happen on the local machine. The application
does not call external services.

---

## Install

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+. Scanned receipts also require
[Tesseract](https://tesseract-ocr.github.io/).

```bash
brew install uv tesseract
uv sync
```

---

## Usage

Put the receipt PDFs and one text-based card statement PDF in a directory, then run:

```bash
uv run receipts-merger run INPUT_DIRECTORY --output OUTPUT_DIRECTORY
```

The statement is detected automatically when unambiguous. Use `--statement PATH` to identify it
explicitly. By default, only accepted matches whose receipt and billed statement currencies differ
are enriched. Pass `--include-same-currency` to enrich accepted same-currency matches too.

Enhanced PDFs include only statement pages containing matched rows. Those pages are rasterized
after unrelated transaction text is individually blacked out, preserving the surrounding layout
while preventing recovery through text extraction or annotation removal.

The output directory contains:

- one PDF for every input receipt, using its original filename;
- `manifest.json`, containing extracted fields, candidate scores, decisions, and unmatched items.

The source statement is not copied into the collection. Receipts that are unmatched, ambiguous, or
not eligible for enrichment are copied byte-for-byte.

Run `uv run receipts-merger --help` or `uv run receipts-merger run --help` for all options.

---

## Review

Ambiguous matches remain in `manifest.json`. To resolve them, create a JSON overrides file:

```json
[
  {
    "receipt_id": "receipt SHA-256",
    "statement_row_ids": ["statement row SHA-256"],
    "status": "accepted",
    "reason": "Reviewed manually"
  }
]
```

Rerun with `--overrides PATH`. Overrides are validated and cannot assign one statement row to
multiple receipts.

---

## Configuration

Pass a TOML file with `--config PATH` to adjust OCR and matching behavior:

```toml
[ocr]
languages = ["eng"]

[parsing]
day_first = true
default_statement_currency = "EUR"

[matching]
days_before = 3
days_after = 10
acceptance_score = 80
minimum_margin = 10
```

---

## Limitations

- The generic statement parser expects selectable text and transaction rows containing a full
  date and amount.
- Included statement pages are rasterized to make redaction permanent, so their text is not
  selectable.
- Receipt OCR quality depends on scan quality and installed Tesseract language data.
- Unsupported layouts and uncertain matches require review; the application deliberately does
  not force a result.

---

## Development

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
uv build
```

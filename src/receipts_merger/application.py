from dataclasses import dataclass
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

from receipts_merger.config import AppConfig
from receipts_merger.documents import discover_pdfs
from receipts_merger.extraction import extract_document
from receipts_merger.manifest import read_manifest, write_manifest
from receipts_merger.matching import match_receipts
from receipts_merger.models import (
    DocumentKind,
    ExtractedDocument,
    MatchDecision,
    MatchStatus,
    Receipt,
    RunManifest,
    StatementRow,
)
from receipts_merger.parsers import parse_receipt, parse_statement
from receipts_merger.rendering import render_composite
from receipts_merger.review import apply_overrides, read_overrides


class PipelineError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RunSummary:
    receipts: int
    accepted: int
    ambiguous: int
    unmatched: int
    enhanced: int
    copied: int


def run_pipeline(
    input_directory: Path,
    output_directory: Path,
    config: AppConfig,
    *,
    statement_path: Path | None = None,
    overrides_path: Path | None = None,
    include_same_currency: bool = False,
) -> RunSummary:
    if input_directory.resolve() == output_directory.resolve():
        raise PipelineError("output directory must differ from the input directory")

    paths = discover_pdfs(input_directory)
    explicit_statement = statement_path.resolve() if statement_path else None
    if explicit_statement and explicit_statement not in {path.resolve() for path in paths}:
        raise PipelineError("statement PDF must be inside the input directory")

    with TemporaryDirectory(prefix="receipts-merger-") as work_directory:
        extracted = tuple(
            extract_document(path, Path(work_directory), config.ocr) for path in paths
        )
        statement, receipt_documents = _select_documents(extracted, explicit_statement)
        receipts = tuple(parse_receipt(document, config.parsing) for document in receipt_documents)
        statement_rows = parse_statement(statement, config.parsing)
        if not statement_rows:
            raise PipelineError("the statement contains no parseable transaction rows")

        result = match_receipts(receipts, statement_rows, config.matching)
        if overrides_path:
            result = apply_overrides(result, read_overrides(overrides_path), statement_rows)

        output_directory.mkdir(parents=True, exist_ok=True)
        previous_outputs = _previous_output_files(output_directory)
        receipts_by_id = {receipt.document_id: receipt for receipt in receipts}
        decisions_by_id = {decision.receipt_id: decision for decision in result.decisions}
        enhanced = 0
        copied = 0
        desired_outputs: set[Path] = set()
        for document in receipt_documents:
            receipt_path = document.document.path
            output_path = output_directory / receipt_path.name
            desired_outputs.add(output_path)
            receipt = receipts_by_id[document.document.id]
            decision = decisions_by_id[document.document.id]
            if _should_enhance(
                receipt,
                decision,
                statement_rows,
                include_same_currency,
            ):
                render_composite(
                    receipt_path,
                    statement.working_path,
                    decision,
                    statement_rows,
                    output_path,
                )
                enhanced += 1
            else:
                _copy_pdf(receipt_path, output_path)
                copied += 1

        for stale_path in previous_outputs - desired_outputs:
            stale_path.unlink(missing_ok=True)

        manifest = RunManifest(
            documents=(
                statement.document,
                *(document.document for document in receipt_documents),
            ),
            receipts=receipts,
            statement_rows=statement_rows,
            candidates=result.candidates,
            decisions=result.decisions,
        )
        write_manifest(manifest, output_directory / "manifest.json")

    statuses = [decision.status for decision in result.decisions]
    return RunSummary(
        receipts=len(receipts),
        accepted=statuses.count(MatchStatus.ACCEPTED),
        ambiguous=statuses.count(MatchStatus.AMBIGUOUS),
        unmatched=statuses.count(MatchStatus.UNMATCHED),
        enhanced=enhanced,
        copied=copied,
    )


def _select_documents(
    extracted: tuple[ExtractedDocument, ...],
    explicit_statement: Path | None,
) -> tuple[ExtractedDocument, tuple[ExtractedDocument, ...]]:
    if explicit_statement:
        statement = next(
            document for document in extracted if document.document.path == explicit_statement
        )
        receipts = tuple(document for document in extracted if document is not statement)
    else:
        statements = tuple(
            document for document in extracted if document.document.kind is DocumentKind.STATEMENT
        )
        if len(statements) != 1:
            raise PipelineError(
                f"expected one statement PDF, detected {len(statements)}; use --statement"
            )
        statement = statements[0]
        receipts = tuple(document for document in extracted if document is not statement)

    if not receipts:
        raise PipelineError("the input directory contains no receipt PDFs")
    statement = _with_kind(statement, DocumentKind.STATEMENT)
    receipts = tuple(_with_kind(document, DocumentKind.RECEIPT) for document in receipts)
    return statement, receipts


def _old_output_name(receipt_path: Path, receipt_id: str) -> str:
    return f"{receipt_path.stem}-{receipt_id[:8]}-composite.pdf"


def _with_kind(
    extracted: ExtractedDocument,
    kind: DocumentKind,
) -> ExtractedDocument:
    return extracted.model_copy(
        update={"document": extracted.document.model_copy(update={"kind": kind})}
    )


def _should_enhance(
    receipt: Receipt,
    decision: MatchDecision,
    rows: tuple[StatementRow, ...],
    include_same_currency: bool,
) -> bool:
    if decision.status is not MatchStatus.ACCEPTED:
        return False
    if include_same_currency:
        return True
    if receipt.total is None:
        return False

    selected_ids = set(decision.statement_row_ids)
    return any(
        row.id in selected_ids and row.billed_amount.currency != receipt.total.currency
        for row in rows
    )


def _copy_pdf(source: Path, destination: Path) -> None:
    temporary_path = destination.with_suffix(f"{destination.suffix}.tmp")
    copyfile(source, temporary_path)
    temporary_path.replace(destination)


def _previous_output_files(output_directory: Path) -> set[Path]:
    manifest_path = output_directory / "manifest.json"
    if not manifest_path.exists():
        return set()
    try:
        manifest = read_manifest(manifest_path)
    except (OSError, ValueError):
        return set()

    paths: set[Path] = set()
    for document in manifest.documents:
        if document.kind is not DocumentKind.RECEIPT:
            continue
        paths.add(output_directory / document.path.name)
        paths.add(output_directory / _old_output_name(document.path, document.id))
    return paths

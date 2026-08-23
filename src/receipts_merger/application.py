from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from receipts_merger.config import AppConfig
from receipts_merger.documents import discover_pdfs
from receipts_merger.extraction import extract_document
from receipts_merger.manifest import write_manifest
from receipts_merger.matching import match_receipts
from receipts_merger.models import (
    DocumentKind,
    ExtractedDocument,
    MatchStatus,
    RunManifest,
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


def run_pipeline(
    input_directory: Path,
    output_directory: Path,
    config: AppConfig,
    *,
    statement_path: Path | None = None,
    overrides_path: Path | None = None,
    full_statement: bool = True,
) -> RunSummary:
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
        receipt_paths = {
            document.document.id: document.document.path for document in receipt_documents
        }
        for decision in result.decisions:
            if decision.status is not MatchStatus.ACCEPTED:
                continue
            receipt_path = receipt_paths[decision.receipt_id]
            output_path = output_directory / _output_name(receipt_path, decision.receipt_id)
            render_composite(
                receipt_path,
                statement.working_path,
                decision,
                statement_rows,
                output_path,
                full_statement=full_statement,
            )

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


def _output_name(receipt_path: Path, receipt_id: str) -> str:
    return f"{receipt_path.stem}-{receipt_id[:8]}-composite.pdf"


def _with_kind(
    extracted: ExtractedDocument,
    kind: DocumentKind,
) -> ExtractedDocument:
    return extracted.model_copy(
        update={"document": extracted.document.model_copy(update={"kind": kind})}
    )

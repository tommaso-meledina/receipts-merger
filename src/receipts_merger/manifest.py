from pathlib import Path

from receipts_merger.models import RunManifest


def write_manifest(manifest: RunManifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(manifest.model_dump_json(indent=2) + "\n")
    temporary_path.replace(path)


def read_manifest(path: Path) -> RunManifest:
    return RunManifest.model_validate_json(path.read_text())

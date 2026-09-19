"""Export segments from the canonical PDF, with page provenance."""

import hashlib
import io
import json
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PyPdfError

from .errors import DocumentError
from .schemas import ParsedDocument, SplitResult


def _write_output(path: Path, data: bytes, *, overwrite: bool) -> None:
    if not overwrite:
        with path.open("xb") as stream:
            stream.write(data)
        return
    # Replace the directory entry instead of following an existing file symlink.
    with tempfile.NamedTemporaryFile(prefix=".jev-docs-", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(data)
            stream.flush()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def export_segments(
    document: ParsedDocument,
    result: SplitResult,
    output_dir: str | Path,
    *,
    overwrite: bool = False,
) -> dict:
    started = time.perf_counter()
    root = Path(output_dir).expanduser().resolve()
    try:
        source_bytes = Path(document.canonical_path).read_bytes()
        actual_hash = hashlib.sha256(source_bytes).hexdigest()
        reader = PdfReader(io.BytesIO(source_bytes))
    except (OSError, ValueError, PyPdfError) as exc:
        raise DocumentError("The canonical source PDF could not be read for export.") from exc
    if (
        len(reader.pages) != document.page_count
        or actual_hash != document.canonical_sha256
        or result.document.get("canonical_sha256") != actual_hash
        or result.document.get("page_count") != document.page_count
    ):
        raise DocumentError("The split result does not match the canonical source PDF.")
    # Public models are mutable and callers can also reload saved result JSON.
    if [page for segment in result.segments for page in segment.pages] != list(
        range(1, document.page_count + 1)
    ):
        raise DocumentError("Segments must cover the canonical source pages exactly once.")
    entries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for segment in result.segments:
        if not segment.pages:
            raise DocumentError("Every exported segment must be nonempty.")
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", segment.id):
            raise DocumentError("Segment IDs must contain only letters, digits, underscores, or hyphens.")
        if segment.id in seen_ids:
            raise DocumentError("Segment IDs must be unique for export.")
        seen_ids.add(segment.id)
        label = re.sub(r"[^a-zA-Z0-9_-]", "_", segment.category)
        filename = f"{segment.id}-{label}.pdf"
        if (root / filename).is_symlink():
            raise DocumentError("Refusing to export over a symbolic link. Choose another directory.")
        if (root / filename).exists() and not overwrite:
            raise DocumentError(
                f"Output exists: {filename}. Choose another directory or --overwrite."
            )
        entries.append(
            {
                "id": segment.id,
                "category": segment.category,
                "pages": segment.pages,
                "file": filename,
            }
        )
    if (root / "manifest.json").is_symlink():
        raise DocumentError("Refusing to export over a symbolic link. Choose another directory.")
    if (root / "manifest.json").exists() and not overwrite:
        raise DocumentError("Output manifest exists. Choose another directory or --overwrite.")
    root.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        writer = PdfWriter()
        for page in entry["pages"]:
            writer.add_page(reader.pages[page - 1])
        buffer = io.BytesIO()
        writer.write(buffer)
        _write_output(root / entry["file"], buffer.getvalue(), overwrite=overwrite)
    manifest = {
        "schema_version": "1",
        "source_sha256": document.source_sha256,
        "canonical_sha256": document.canonical_sha256,
        "segments": entries,
    }
    _write_output(root / "manifest.json", json.dumps(manifest, indent=2).encode(), overwrite=overwrite)
    result.metrics.export_ms = (time.perf_counter() - started) * 1000
    result.metrics.total_ms += result.metrics.export_ms
    return manifest

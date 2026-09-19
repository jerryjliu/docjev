"""Content-addressed local artifacts. Cache contents may contain document text."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .schemas import ParsedDocument

CACHE_SCHEMA = "jev-docs-ocr-v1"


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_key(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def cache_root(directory: str | Path | None = None) -> Path:
    root = Path(directory or ".jev-docs/cache").expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_document(root: Path, key: str, canonical: Path, *, max_age_seconds: float | None = None) -> ParsedDocument | None:
    try:
        record = root / "ocr" / f"{key}.json"
        if max_age_seconds is not None and time.time() - record.stat().st_mtime > max_age_seconds:
            return None
        doc = ParsedDocument.model_validate_json(record.read_text())
        if not canonical.is_file() or digest_file(canonical) != doc.canonical_sha256:
            return None
        # Relocation of an intact cache must not leak the former machine's path.
        doc.canonical_path = str(canonical)
        return doc
    except (OSError, ValueError, ValidationError):
        return None


def save_document(root: Path, key: str, document: ParsedDocument) -> None:
    atomic_write(root / "ocr" / f"{key}.json", document.model_dump_json(indent=2).encode())

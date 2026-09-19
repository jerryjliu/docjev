"""Internal OCR contract before common page validation."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any

from ..schemas import ParserInfo, RequestRecord

NORMALIZATION_VERSION = "unicode-nfc-lines-v1"


@dataclass
class OCRPage:
    number: int
    text: str
    markdown: str | None = None


@dataclass
class OCRResult:
    pages: list[OCRPage]
    total_pages: int
    parser: ParserInfo
    cost_usd: float | None = None
    cost_status: str = "unknown"
    requests: list[RequestRecord] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()

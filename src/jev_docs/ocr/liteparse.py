"""Native LiteParse Python bindings with local OCR enabled."""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

from ..errors import DocumentError
from ..schemas import ParserInfo
from .base import NORMALIZATION_VERSION, OCRPage, OCRResult, normalize_text

OPTIONS = {"ocr_enabled": True, "ocr_language": "en", "continue_on_page_error": False,
           "ocr_failure_fatal": True, "quiet": True, "normalization": NORMALIZATION_VERSION}


def parser_info() -> ParserInfo:
    return ParserInfo(name="liteparse", version=version("liteparse"), options=OPTIONS.copy())


def parse_pdf(path: Path, page_count: int, *, disable_cache: bool = False) -> OCRResult:
    from liteparse import LiteParse

    options = {key: value for key, value in OPTIONS.items() if key != "normalization"}
    try:
        result = LiteParse(**options).parse(path)
    except Exception as exc:
        raise DocumentError("LiteParse failed to read this PDF. Check local OCR readiness with docjev doctor; scanned files may need the initial language-data download.") from exc
    if result.page_errors:
        numbers = ", ".join(str(getattr(error, "page_num", "unknown")) for error in result.page_errors)
        raise DocumentError(f"LiteParse failed on page(s) {numbers}; partial OCR cannot be classified or split.")
    return OCRResult(
        pages=[OCRPage(number=page.page_num, text=normalize_text(page.text),
                       markdown=normalize_text(page.markdown) or None) for page in result.pages],
        total_pages=result.total_pages,
        parser=parser_info(), cost_usd=0.0, cost_status="not_applicable",
    )

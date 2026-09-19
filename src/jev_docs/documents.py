"""Read complete documents into the shared page-preserving representation."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from .cache import CACHE_SCHEMA, cache_key, cache_root, digest_file, load_document, save_document
from .conversion import canonicalize, is_visually_blank
from .errors import DocumentError
from .ocr.base import OCRResult
from .schemas import Page, ParsedDocument, RunMetrics


def validate_pages(result: OCRResult, canonical_path: Path, page_count: int) -> list[Page]:
    if result.total_pages != page_count:
        raise DocumentError(f"OCR reported {result.total_pages} pages; the canonical PDF has {page_count}. No partial result was accepted.")
    expected = list(range(1, page_count + 1))
    if [page.number for page in result.pages] != expected:
        raise DocumentError("OCR pages are missing, duplicated, out of order, or outside the source range. No partial result was accepted.")
    pages = []
    for page in result.pages:
        blank = False
        if not page.text.strip():
            blank = is_visually_blank(canonical_path, page.number)
            if not blank:
                raise DocumentError(f"Page {page.number} contains visible content but has no readable text. Try LlamaParse OCR or a clearer scan.")
        pages.append(Page(number=page.number, text=page.text, markdown=page.markdown, blank=blank))
    return pages


def parse_document(path: str | Path, *, ocr: str = "liteparse", tier: str = "agentic",
                   parser_version: str = "latest", cache_dir: str | Path | None = None,
                   use_cache: bool = True,
                   progress: Callable[[str], None] | None = None) -> ParsedDocument:
    """OCR every page. ``use_cache=False`` also disables LlamaParse's server cache.

    Canonical PDFs are retained even when OCR caching is disabled, so segment exports
    and previews keep the exact pagination used for the decision.
    """
    start = time.perf_counter()
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise DocumentError("Input document does not exist or is not a file.")
    if not source.stat().st_size:
        raise DocumentError("The input document is empty.")
    if ocr == "liteparse":
        from .ocr import liteparse as adapter
        info = adapter.parser_info()
    elif ocr == "llamaparse":
        from .ocr import llamaparse as cloud_adapter
        info = cloud_adapter.parser_info(tier, parser_version)
    else:
        raise DocumentError("OCR must be liteparse or llamaparse.")
    root = cache_root(cache_dir)
    source_hash = digest_file(source)
    if progress:
        progress("converting")
    conversion_start = time.perf_counter()
    canonical = canonicalize(source, root, use_cache=use_cache)
    conversion_ms = (time.perf_counter() - conversion_start) * 1000
    info.conversion = canonical.conversion
    key = cache_key({"schema": CACHE_SCHEMA, "canonical_sha256": canonical.sha256,
                     "parser": info.model_dump()})
    if use_cache:
        # A mutable remote version alias must not keep an indefinite local snapshot.
        max_age = 24 * 3600 if ocr == "llamaparse" and parser_version == "latest" else None
        cached = load_document(root, key, canonical.path, max_age_seconds=max_age)
        if cached:
            cached.source_name = source.name
            cached.source_sha256 = source_hash
            cached.metrics = RunMetrics(conversion_ms=conversion_ms, ocr_cache_hit=True,
                                        ocr_cost_usd=0, ocr_cost_status="not_applicable",
                                        total_ms=(time.perf_counter() - start) * 1000)
            if progress:
                progress("ocr_cached")
            return cached
    if progress:
        progress("ocr")
    ocr_start = time.perf_counter()
    if ocr == "liteparse":
        result = adapter.parse_pdf(canonical.path, canonical.page_count, disable_cache=not use_cache)
    else:
        result = cloud_adapter.parse_pdf(canonical.path, canonical.page_count, tier=tier,
                                         parser_version=parser_version, disable_cache=not use_cache)
    ocr_ms = (time.perf_counter() - ocr_start) * 1000
    validation_start = time.perf_counter()
    pages = validate_pages(result, canonical.path, canonical.page_count)
    validation_ms = (time.perf_counter() - validation_start) * 1000
    result.parser.conversion = canonical.conversion
    document = ParsedDocument(
        source_name=source.name, source_sha256=source_hash,
        canonical_path=str(canonical.path), canonical_sha256=canonical.sha256,
        page_count=canonical.page_count, pages=pages, parser=result.parser,
        metrics=RunMetrics(conversion_ms=conversion_ms, ocr_ms=ocr_ms,
                           validation_ms=validation_ms, total_ms=(time.perf_counter() - start) * 1000,
                           ocr_cost_usd=result.cost_usd, ocr_cost_status=result.cost_status,
                           requests=result.requests),
    )
    if use_cache:
        save_document(root, key, document)
    return document

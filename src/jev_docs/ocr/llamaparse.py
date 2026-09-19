"""Optional LlamaParse Parse v2 adapter; no Classify or Split service calls."""

from __future__ import annotations

import os
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from ..errors import DocumentError, ProviderError
from ..schemas import ParserInfo, RequestRecord
from .base import NORMALIZATION_VERSION, OCRPage, OCRResult, normalize_text

TIERS = {"cost-effective": "cost_effective", "agentic": "agentic", "agentic-plus": "agentic_plus"}
CREDITS_PER_PAGE = {"cost_effective": 3, "agentic": 10, "agentic_plus": 45}
USD_PER_CREDIT = 0.00125  # Published list rate, checked 2026-09-18. Discounts are not inferred.


def normalize_tier(tier: str) -> str:
    normalized = TIERS.get(tier, tier)
    if normalized not in CREDITS_PER_PAGE:
        raise DocumentError("LlamaParse tier must be cost-effective, agentic, or agentic-plus.")
    return normalized


def parser_info(tier: str, parser_version: str) -> ParserInfo:
    tier = normalize_tier(tier)
    try:
        sdk_version = version("llama-cloud")
    except PackageNotFoundError as exc:
        raise DocumentError("Install the optional LlamaParse integration: pip install 'docjev[llamaparse]'.") from exc
    return ParserInfo(name="llamaparse", version=parser_version, tier=tier,
                      options={"sdk_version": sdk_version, "requested_version": parser_version,
                               "normalization": NORMALIZATION_VERSION,
                               "output": "page-markdown-with-headers-footers", "max_retries": 0})


def parse_pdf(path: Path, page_count: int, *, tier: str, parser_version: str,
              disable_cache: bool = False) -> OCRResult:
    info = parser_info(tier, parser_version)
    if not os.environ.get("LLAMA_CLOUD_API_KEY"):
        raise ProviderError("Set LLAMA_CLOUD_API_KEY to use LlamaParse OCR.")
    from llama_cloud import LlamaCloud

    start = time.perf_counter()
    try:
        with LlamaCloud(max_retries=0, timeout=180) as client:
            # Use a neutral upload filename; source names never reach decision prompts.
            with path.open("rb") as stream:
                uploaded = client.files.create(file=("document.pdf", stream, "application/pdf"), purpose="parse")
            result = client.parsing.parse(
                file_id=uploaded.id, tier=info.tier or "agentic", version=parser_version,
                expand=["markdown", "usage", "job_metadata"], disable_cache=disable_cache,
                timeout=300, verbose=False,
            )
    except Exception as exc:
        # SDK errors may contain request details: only safe, actionable metadata is exposed.
        status = getattr(exc, "status_code", None)
        suffix = f" (HTTP {status})" if isinstance(status, int) else ""
        raise ProviderError(f"LlamaParse request failed{suffix}. Check the API key, project access, tier/version, and provider status.") from exc
    if result.job.status != "COMPLETED" or result.markdown is None:
        raise DocumentError("LlamaParse did not return a completed page-level Markdown result.")
    failed = [page.page_number for page in result.markdown.pages if not page.success]
    if failed:
        raise DocumentError(f"LlamaParse failed on page(s) {', '.join(map(str, failed))}; partial OCR cannot be classified or split.")
    pages = []
    for page in result.markdown.pages:
        # Footer and header are distinct fields in Parse v2. Preserve them for boundaries.
        content = "\n\n".join(part for part in
                              (getattr(page, "header", None), getattr(page, "markdown", ""),
                               getattr(page, "footer", None)) if part)
        content = normalize_text(content)
        pages.append(OCRPage(number=page.page_number, text=content, markdown=content or None))
    credits = result.job.usage.credits if result.job.usage else None
    cost = credits * USD_PER_CREDIT if credits is not None else None
    raw_parameters = result.raw_parameters or {}
    resolved = raw_parameters.get("version")
    if isinstance(resolved, str) and resolved != "latest":
        info.version = resolved
    info.options["version_resolved"] = info.version != "latest"
    info.options["server_cache_disabled"] = disable_cache
    info.options["usage"] = {"credits": credits, "list_price_usd_per_credit": USD_PER_CREDIT,
                              "price_date": "2026-09-18",
                              "list_cost_estimate_if_usage_unavailable": page_count * CREDITS_PER_PAGE[info.tier or "agentic"] * USD_PER_CREDIT}
    elapsed = (time.perf_counter() - start) * 1000
    return OCRResult(pages=pages, total_pages=len(pages), parser=info, cost_usd=cost,
                     cost_status="estimated" if cost is not None else "unknown",
                     requests=[RequestRecord(provider="llamaparse", model=f"{info.tier}/{info.version}",
                                             task="ocr", request_id=result.job.id,
                                             elapsed_ms=elapsed, cost_usd=cost,
                                             cost_status="estimated" if cost is not None else "unknown")])

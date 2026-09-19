"""Contiguous document-instance segmentation, including same-category neighbors."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from .engines import make_engine
from .errors import ProviderError
from .schemas import PageDecision, ParsedDocument, RuleSet, Segment, SplitResult
from .telemetry import finish_metrics


def assemble_segments(
    decisions: list[PageDecision],
    document: ParsedDocument,
    rules: RuleSet,
    min_probability: float = 0.7,
) -> tuple[list[Segment], list[str]]:
    if [d.page for d in decisions] != list(range(1, document.page_count + 1)):
        raise ProviderError("The engine returned missing, duplicate, or unordered page decisions.")
    segments: list[Segment] = []
    warnings: list[str] = []
    probabilities: list[list[float]] = []
    for page, decision in zip(document.pages, decisions, strict=True):
        if decision.category not in rules.criteria:
            raise ProviderError("The engine returned an unknown page category.")
        if page.blank:
            decision.category = "other"
            decision.category_probability = None
            decision.probabilities = None
            decision.provider_confidence = None
            decision.starts_document = page.number == 1 or not document.pages[page.number - 2].blank
        changed = bool(segments and decision.category != segments[-1].category)
        conflict = changed and not decision.starts_document
        if conflict:
            warnings.append(
                f"Page {decision.page}: category change overrode a continuation decision."
            )
        after_blank = page.number > 1 and document.pages[page.number - 2].blank and not page.blank
        if not segments or changed or decision.starts_document or after_blank:
            segments.append(
                Segment(
                    id=f"segment-{len(segments) + 1:03d}",
                    category=decision.category,
                    pages=[decision.page],
                )
            )
            probabilities.append([])
        else:
            segments[-1].pages.append(decision.page)
        probability = decision.category_probability
        if probability is not None:
            probabilities[-1].append(probability)
        if (
            conflict
            or decision.category == "other"
            or (probability is not None and probability < min_probability)
        ):
            segments[-1].needs_review = True
    for segment, values in zip(segments, probabilities, strict=True):
        segment.mean_category_probability = sum(values) / len(values) if values else None
    return segments, warnings


async def asplit_document(
    document: str | Path | ParsedDocument,
    rules: RuleSet,
    *,
    engine: Any = "jev",
    model: str | None = None,
    boundary_threshold: float = 0.5,
    min_probability: float = 0.7,
    **parse_options,
) -> SplitResult:
    if not 0 <= boundary_threshold <= 1 or not 0 <= min_probability <= 1:
        raise ValueError("Thresholds must be between 0 and 1")
    started = time.perf_counter()
    from .documents import parse_document

    pre_parsed = isinstance(document, ParsedDocument)
    if isinstance(document, ParsedDocument):
        doc = document
    else:
        doc = await asyncio.to_thread(parse_document, document, **parse_options)
    owned = isinstance(engine, str)
    service = make_engine(engine, model) if owned else engine
    decision_start = time.perf_counter()
    try:
        decisions, requests = await service.split(doc, rules, boundary_threshold=boundary_threshold)
    finally:
        if owned:
            await service.aclose()
    decision_ms = (time.perf_counter() - decision_start) * 1000
    validation_start = time.perf_counter()
    try:
        segments, warnings = assemble_segments(decisions, doc, rules, min_probability)
    except ProviderError as exc:
        raise ProviderError(str(exc), requests=requests) from None
    total_ms = (time.perf_counter() - started) * 1000 + (doc.metrics.total_ms if pre_parsed else 0)
    return SplitResult(
        segments=segments,
        page_decisions=decisions,
        warnings=warnings,
        document=doc.public_info(),
        engine=service.name,
        model=requests[-1].model if requests else service.model,
        metrics=finish_metrics(
            doc,
            requests,
            decision_ms=decision_ms,
            validation_ms=(time.perf_counter() - validation_start) * 1000,
            total_ms=total_ms,
        ),
    )


def split_document(document: str | Path | ParsedDocument, rules: RuleSet, **options) -> SplitResult:
    return asyncio.run(asplit_document(document, rules, **options))

"""Contiguous document-instance segmentation, including same-category neighbors."""

from __future__ import annotations

import asyncio
import math
import time
from pathlib import Path
from typing import Any

from .engines import make_engine
from .errors import ProviderError
from .schemas import PageDecision, ParsedDocument, ReviewReason, RuleSet, Segment, SplitResult
from .telemetry import finish_metrics


def assemble_segments(
    decisions: list[PageDecision],
    document: ParsedDocument,
    rules: RuleSet,
    min_probability: float = 0.7,
    *,
    boundary_threshold: float = 0.5,
    boundary_review_margin: float = 0.1,
) -> tuple[list[Segment], list[str]]:
    _validate_thresholds(min_probability, boundary_threshold, boundary_review_margin)
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
            decision.starts_document_probability = None
        changed = bool(segments and decision.category != segments[-1].category)
        conflict = changed and not decision.starts_document
        if conflict:
            warnings.append(
                f"Page {decision.page}: category change overrode a continuation decision."
            )
        after_blank = page.number > 1 and document.pages[page.number - 2].blank and not page.blank
        previous_segment = segments[-1] if segments else None
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
        if conflict:
            _flag(segments[-1], ReviewReason(code="category_boundary_conflict", page=decision.page))
        if decision.category == "other":
            _flag(segments[-1], ReviewReason(code="other_category", page=decision.page))
        if probability is not None and probability < min_probability:
            _flag(segments[-1], ReviewReason(code="category_uncertain", page=decision.page,
                                           probability=probability, threshold=min_probability))
        boundary_probability = decision.starts_document_probability
        # The first page and deterministic blank-page boundaries are not model decisions.
        if (previous_segment is not None and not page.blank and not after_blank
                and boundary_probability is not None and boundary_review_margin > 0):
            distance = abs(boundary_probability - boundary_threshold)
            if distance < boundary_review_margin or math.isclose(distance, boundary_review_margin):
                reason = ReviewReason(code="boundary_near_threshold", page=decision.page,
                                      probability=boundary_probability, threshold=boundary_threshold)
                _flag(segments[-1], reason)
                # An uncertain cut affects both documents, including same-category neighbors.
                if previous_segment is not segments[-1]:
                    _flag(previous_segment, reason.model_copy())
    for segment, values in zip(segments, probabilities, strict=True):
        segment.mean_category_probability = sum(values) / len(values) if values else None
    return segments, warnings


def _flag(segment: Segment, reason: ReviewReason) -> None:
    segment.needs_review = True
    segment.review_reasons.append(reason)


def _validate_thresholds(min_probability: float, boundary_threshold: float,
                         boundary_review_margin: float) -> None:
    if not 0 <= boundary_threshold <= 1 or not 0 <= min_probability <= 1:
        raise ValueError("Thresholds must be between 0 and 1")
    if not 0 <= boundary_review_margin <= 0.5:
        raise ValueError("Boundary review margin must be between 0 and 0.5")


async def asplit_document(
    document: str | Path | ParsedDocument,
    rules: RuleSet,
    *,
    engine: Any = "jev",
    model: str | None = None,
    boundary_threshold: float = 0.5,
    min_probability: float = 0.7,
    boundary_review_margin: float = 0.1,
    **parse_options,
) -> SplitResult:
    _validate_thresholds(min_probability, boundary_threshold, boundary_review_margin)
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
        segments, warnings = assemble_segments(
            decisions, doc, rules, min_probability,
            boundary_threshold=boundary_threshold, boundary_review_margin=boundary_review_margin,
        )
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

"""Classify an entire document against natural-language category rules."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from .engines import make_engine
from .errors import DocumentError, ProviderError
from .schemas import ClassificationResult, ParsedDocument, RuleSet
from .telemetry import finish_metrics


async def aclassify_document(
    document: str | Path | ParsedDocument,
    rules: RuleSet,
    *,
    engine: Any = "jev",
    model: str | None = None,
    min_probability: float = 0.7,
    **parse_options,
) -> ClassificationResult:
    if not 0 <= min_probability <= 1:
        raise ValueError("min_probability must be between 0 and 1")
    started = time.perf_counter()
    from .documents import parse_document

    pre_parsed = isinstance(document, ParsedDocument)
    if isinstance(document, ParsedDocument):
        doc = document
    else:
        doc = await asyncio.to_thread(parse_document, document, **parse_options)
    if all(p.blank for p in doc.pages):
        raise DocumentError("The document is blank; no model classification was attempted.")
    owned = isinstance(engine, str)
    service = make_engine(engine, model) if owned else engine
    decision_start = time.perf_counter()
    try:
        answer, requests = await service.classify(doc, rules)
    finally:
        if owned:
            await service.aclose()
    decision_ms = (time.perf_counter() - decision_start) * 1000
    validation_start = time.perf_counter()
    if answer.category not in rules.criteria:
        raise ProviderError(
            "The engine returned a category outside the configured rules.", requests=requests
        )
    probability = answer.probabilities.get(answer.category) if answer.probabilities else None
    needs_review = answer.category == "other" or (
        probability is not None and probability < min_probability
    )
    warnings = (
        ["Review threshold is an operational setting, not an empirically calibrated guarantee."]
        if needs_review
        else []
    )
    total_ms = (time.perf_counter() - started) * 1000 + (doc.metrics.total_ms if pre_parsed else 0)
    return ClassificationResult(
        category=answer.category,
        category_probability=probability,
        probabilities=answer.probabilities,
        provider_confidence=answer.provider_confidence,
        needs_review=needs_review,
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


def classify_document(
    document: str | Path | ParsedDocument, rules: RuleSet, **options
) -> ClassificationResult:
    """Synchronous convenience API; use aclassify_document inside an event loop."""
    return asyncio.run(aclassify_document(document, rules, **options))

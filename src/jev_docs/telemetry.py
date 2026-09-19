"""Stage timing and cost rollups, preserving unknown charges."""

from .schemas import ParsedDocument, RequestRecord, RunMetrics


def finish_metrics(
    document: ParsedDocument,
    requests: list[RequestRecord],
    *,
    decision_ms: float,
    validation_ms: float,
    total_ms: float,
) -> RunMetrics:
    metrics = document.metrics.model_copy(deep=True)
    metrics.requests = document.metrics.requests + requests
    metrics.decision_ms = round(decision_ms, 3)
    metrics.validation_ms = round(validation_ms, 3)
    metrics.total_ms = round(total_ms, 3)
    metrics.decision_cost_usd = (
        sum(r.cost_usd or 0 for r in requests)
        if all(r.cost_usd is not None for r in requests)
        else None
    )
    return metrics

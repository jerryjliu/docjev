"""Hand-computed task metrics, especially same-category boundaries and failures."""

import pytest

from benchmarks.metrics import (
    bootstrap_mean,
    label_metrics,
    percentile,
    prf,
    split_metrics,
    summarize,
)


def segment(category, *pages):
    return {"category": category, "pages": list(pages)}


def test_classification_failures_are_in_denominator_and_recall():
    metrics = label_metrics(["invoice", "invoice", "contract", "contract"],
                            ["invoice", "contract", "contract", None], ["invoice", "contract"])
    assert metrics["accuracy"] == 0.5
    assert metrics["per_class"]["invoice"]["recall"] == 0.5
    assert metrics["per_class"]["invoice"]["precision"] == 1
    assert metrics["confusion_matrix"]["contract"]["__missing__"] == 1
    assert metrics["macro_f1"] == pytest.approx((2 / 3 + 0.5) / 2)


def test_same_category_boundary_is_a_real_document_boundary():
    truth = [[segment("invoice", 1, 2), segment("invoice", 3, 4), segment("letter", 5)]]
    prediction = [[segment("invoice", 1, 2, 3, 4), segment("letter", 5)]]
    result = split_metrics(truth, prediction, [5])
    assert result["page_accuracy"] == 1
    assert result["packet_exact_match"] == 0
    assert result["boundary"]["precision"] == 1
    assert result["boundary"]["recall"] == 0.5
    assert result["boundary"]["f1"] == pytest.approx(2 / 3)
    assert result["segment"]["f1"] == pytest.approx(2 / 5)
    assert result["same_category_boundary_recall"] == 0


def test_failed_packet_loses_all_pages_segments_and_boundaries():
    truth = [[segment("invoice", 1), segment("letter", 2)]]
    result = split_metrics(truth, [None], [2])
    assert result["page_accuracy"] == 0
    assert result["packet_exact_match"] == 0
    assert result["coverage_validity"] == 0
    assert result["boundary"]["recall"] == 0
    assert result["segment"]["recall"] == 0


def test_invalid_coverage_is_not_accepted_as_a_good_split():
    truth = [[segment("invoice", 1, 2)]]
    result = split_metrics(truth, [[segment("invoice", 1), segment("invoice", 1)]], [2])
    assert result["page_accuracy"] == 0
    assert result["coverage_validity"] == 0


def test_no_boundary_conventions_are_explicit():
    result = split_metrics([[segment("invoice", 1, 2)]], [[segment("invoice", 1, 2)]], [2])
    assert result["boundary"]["f1"] == 1
    assert result["same_category_boundary_recall"] is None
    assert prf(0, 0, 0)["precision"] == 1
    assert prf(0, 2, 0)["f1"] == 0
    assert percentile([], .95) is None
    assert percentile([10, 20], .95) == pytest.approx(19.5)
    assert bootstrap_mean([1.0]) is None


def test_summary_uses_first_pass_quality_and_all_successful_latencies():
    rows = []
    for repeat, category, timing in [(0, "invoice", 10), (1, "contract", 30)]:
        rows.append({"task": "classify", "id": "a", "engine": "jev", "model": "jev-1.13.0",
                     "scope": "decision", "concurrency": 1, "phase": "measured", "repeat": repeat,
                     "status": "ok", "wall_ms": timing, "requests": [],
                     "result": {"category": category, "needs_review": False,
                                "metrics": {"decision_ms": timing}}})
    # A not-yet-recorded source must still count against an interrupted report's denominator.
    data = {"classify": [{"id": "a", "split": "test", "category": "invoice"},
                         {"id": "b", "split": "test", "category": "contract"}]}
    result = summarize(rows, data)["groups"][0]
    assert result["accuracy"] == 0.5
    assert result["planned_unique"] == 2
    assert result["decision_p50_ms"] == 20
    assert result["latency_samples"] == 2
    assert result["repeat_disagreement_documents"] == 1


@pytest.mark.asyncio
async def test_budget_reserves_in_flight_and_retains_unknown_charges():
    from benchmarks.run import Budget

    budget = Budget(1)
    assert await budget.reserve(.7)
    assert not await budget.reserve(.4)
    await budget.settle(.7, [{"cost_usd": None}], dispatched=True)
    assert budget.unknown_reserved == .7
    assert not await budget.reserve(.4)
    assert await budget.reserve(.2)
    await budget.settle(.2, [{"cost_usd": .05}], dispatched=True)
    assert budget.known == .05
    assert budget.committed == pytest.approx(.75)

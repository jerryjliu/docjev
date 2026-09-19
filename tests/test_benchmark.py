"""Run the complete recorder/reporter with fake decisions; never call providers."""

import json

import pytest

from benchmarks import run as runner
from jev_docs.schemas import ClassificationResult, RequestRecord, RunMetrics, Segment, SplitResult


@pytest.mark.asyncio
async def test_recorder_keeps_ocr_shared_and_costs_separate(tmp_path, monkeypatch, document):
    class FakeEngine:
        name = "fixture"

        def __init__(self, model, **_):
            self.model = model

        async def aclose(self):
            return None

    monkeypatch.setattr(runner, "JevEngine", FakeEngine)
    monkeypatch.setattr(runner, "OpenAIEngine", FakeEngine)
    calls = []

    def parse(*_, **__):
        parsed = document.model_copy(deep=True)
        parsed.metrics = RunMetrics(ocr_ms=9500, total_ms=9500, ocr_cost_usd=9,
                                   requests=[RequestRecord(provider="llamaparse", model="test", task="ocr", cost_usd=9)])
        return parsed

    monkeypatch.setattr(runner, "parse_document", parse)

    async def classify(parsed, rules, *, engine, **_):
        assert parsed.metrics.ocr_ms == parsed.metrics.total_ms == parsed.metrics.ocr_cost_usd == 0
        assert parsed.metrics.requests == []
        calls.append([page.text for page in parsed.pages])
        return ClassificationResult(category="invoice", document=parsed.public_info(),
                                    engine="fixture", model=engine.model,
                                    metrics=RunMetrics(decision_ms=3, requests=[RequestRecord(
                                        provider="fixture", model=engine.model, task="classify", cost_usd=.001)]))

    async def split(parsed, rules, *, engine, **_):
        assert parsed.metrics.requests == []
        calls.append([page.text for page in parsed.pages])
        return SplitResult(segments=[Segment(id="segment-001", category="invoice", pages=[1, 2]),
                                     Segment(id="segment-002", category="invoice", pages=[3, 4])],
                           document=parsed.public_info(), engine="fixture", model=engine.model,
                           metrics=RunMetrics(decision_ms=4, requests=[RequestRecord(
                               provider="fixture", model=engine.model, task="split", cost_usd=.002)]))

    monkeypatch.setattr(runner, "aclassify_document", classify)
    monkeypatch.setattr(runner, "asplit_document", split)
    config = runner.load_config(runner.ROOT / "benchmarks/configs/default.yaml")
    config.update(repeats=2, warmups=0)
    datasets = {
        "classify": [{"id": "fake-classify", "split": "test", "category": "invoice", "page_count": 4, "path": "unused.pdf"}],
        "split": [{"id": "fake-split", "split": "test", "page_count": 4, "path": "unused.pdf",
                   "segments": [{"category": "invoice", "pages": [1, 2]}, {"category": "invoice", "pages": [3, 4]}]}],
    }
    output = tmp_path / "fake-run"
    summary = await runner.run(config, datasets, output)
    assert len(summary["groups"]) == 4
    assert all(group["completion_rate"] == 1 for group in summary["groups"])
    assert summary["budget"]["known_cost_usd"] == pytest.approx(.012)
    rows = [json.loads(line) for line in (output / "raw.jsonl").read_text().splitlines()]
    assert len(rows) == 8
    assert len({row["parsed_pages_sha256"] for row in rows}) == 1
    assert all(row["result"]["metrics"]["ocr_cost_usd"] is None for row in rows)
    assert all(content == calls[0] for content in calls)
    assert (output / "report.md").is_file() and (output / "latency.svg").is_file()


def test_dry_run_is_local_and_respects_frozen_hashes():
    config = runner.load_config(runner.ROOT / "benchmarks/configs/default.yaml")
    datasets = runner.load_datasets(config, limit=1)
    plan = runner.dry_run(config, datasets)
    assert plan["remote_calls"] == 0
    assert plan["tasks"]["classify"]["measured_task_calls"] == 10
    assert plan["tasks"]["split"]["test_documents"] == 1

"""Bounded prepared execution with fake providers only."""

import asyncio
import json

import pytest

from benchmarks import prepare
from benchmarks import run as runner
from jev_docs.errors import ProviderError
from jev_docs.schemas import ClassificationResult, RequestRecord, RunMetrics, Segment, SplitResult


@pytest.fixture
def prepared_run(tmp_path, monkeypatch, document, rules):
    config = runner.load_config(runner.ROOT / "benchmarks/configs/real-small-v1.yaml")
    config["cleanup_timeout_s"] = .02
    dataset = {"classify": [], "split": []}
    docs = {}
    entries = {}
    for task, count in (("classify", 40), ("split", 8)):
        for index in range(count + 1):
            source_id = f"{task}-{index}"
            item = {"id": source_id, "split": "dev" if index == 0 else "test", "page_count": 4,
                    "path": f"{source_id}.pdf", "sha256": "fixture"}
            if task == "classify":
                item["category"] = "invoice"
            else:
                item["segments"] = [{"category": "invoice", "pages": [1, 2]},
                                    {"category": "invoice", "pages": [3, 4]}]
            dataset[task].append(item)
            parsed = document.model_copy(deep=True)
            parsed.source_name = f"{source_id}.pdf"
            parsed.metrics = RunMetrics(ocr_ms=42, total_ms=42)
            for page in parsed.pages:
                page.text = f"{source_id}: unchanged source page {page.number}"
            docs[source_id] = parsed
            entries[source_id] = {"status": "ok", "pages_sha256": source_id,
                                  "preparation_metrics": parsed.metrics.model_dump(),
                                  "engine_preflight": {name: {"status": "ok", "request_count": 1}
                                                       for name in ("jev", "openai")}}
        for kind, value in (("manifest", json.dumps(dataset[task])), ("rules", rules.model_dump_json())):
            path = tmp_path / config["tasks"][task][kind]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)
    (tmp_path / "benchmarks").mkdir(exist_ok=True)
    (tmp_path / "benchmarks/pricing.json").write_text('{"as_of":"fixture"}')
    (tmp_path / "uv.lock").write_text("fixture lock")
    receipt = {"status": "ready", "execution_plan": runner.build_execution_plan(config, dataset),
               "items": entries, "receipt_sha256": "fixture"}
    receipt_path = tmp_path / "preparation.json"
    receipt_path.write_text(json.dumps(receipt))
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(prepare, "validate_profile", lambda *args, **kwargs: None)
    monkeypatch.setattr(prepare, "load_prepared", lambda *args, **kwargs: (receipt, docs))
    claims = []

    def claim(*args, **kwargs):
        if claims:
            raise ValueError("Receipt already claimed")
        claims.append(args)

    monkeypatch.setattr(prepare, "claim_prepared", claim)
    monkeypatch.setattr(runner, "parse_document", lambda *args, **kwargs: pytest.fail("Live receipt execution reparsed OCR"))
    created = []
    calls = []

    class FakeEngine:
        def __init__(self, model, **options):
            self.model = model
            self.name = "jev" if model.startswith("jev") else "openai"
            self.options = options
            self.closed = False
            created.append(self)

        async def aclose(self):
            self.closed = True

    monkeypatch.setattr(runner, "JevEngine", FakeEngine)
    monkeypatch.setattr(runner, "OpenAIEngine", FakeEngine)

    async def decision(parsed, config_rules, *, engine, **options):
        assert parsed.metrics.ocr_ms == parsed.metrics.total_ms == 0
        assert parsed.metrics.requests == []
        assert parsed.pages[0].text.endswith("unchanged source page 1")
        assert config_rules.categories[0].description == rules.categories[0].description
        calls.append((parsed.source_name, engine.name))
        parsed.pages[0].text = "MUTATED PRIVATE COPY"
        config_rules.categories[0].description = "MUTATED PRIVATE COPY"
        metrics = RunMetrics(decision_ms=2, requests=[RequestRecord(
            provider=engine.name, model=engine.model, task="split" if parsed.source_name.startswith("split") else "classify",
            input_tokens=20, cost_usd=.001, cost_status="estimated",
        )])
        if parsed.source_name.startswith("classify"):
            return ClassificationResult(category="invoice", engine=engine.name, model=engine.model,
                                        document=parsed.public_info(), metrics=metrics)
        return SplitResult(segments=[Segment(id="segment-001", category="invoice", pages=[1, 2]),
                                     Segment(id="segment-002", category="invoice", pages=[3, 4])],
                           engine=engine.name, model=engine.model, document=parsed.public_info(), metrics=metrics)

    monkeypatch.setattr(runner, "aclassify_document", decision)
    monkeypatch.setattr(runner, "asplit_document", decision)
    return {"config": config, "dataset": dataset, "receipt": receipt, "path": receipt_path,
            "docs": docs, "created": created, "calls": calls, "claims": claims,
            "decision": decision, "output": tmp_path / "run"}


async def execute(fixture):
    return await runner.run(fixture["config"], fixture["dataset"], fixture["output"], prepared_path=fixture["path"])


def files(fixture):
    output = fixture["output"]
    manifest = json.loads((output / "manifest.json").read_text())
    rows = [json.loads(line) for line in (output / "raw.jsonl").read_text().splitlines()]
    events = [json.loads(line) for line in (output / "events.jsonl").read_text().splitlines()]
    return manifest, rows, events


async def test_prepared_run_performs_exactly_one_hundred_calls_and_no_ocr(prepared_run):
    data = prepared_run
    summary = await execute(data)
    manifest, rows, events = files(data)
    assert manifest["status"] == summary["run_status"] == "complete"
    assert len(data["calls"]) == len(rows) == len(events) == 100
    assert sum(row["phase"] == "warmup" for row in rows) == 4
    assert len({row["observation_id"] for row in rows}) == 100
    assert all(row["id"] == row["source_id"] for row in rows)
    assert all(row["requests"] and row["request_count_complete"] for row in rows)
    assert all(event["event"] == "dispatch_started" and event["reserved_cost_usd"] > 0 for event in events)
    assert all(engine.closed for engine in data["created"])
    assert all(engine.options["timeout"] == 30 for engine in data["created"])
    assert data["created"][0].options["context_recovery"] is False
    assert manifest["budget"]["known_cost_usd"] == pytest.approx(.1)
    assert all(doc.metrics.ocr_ms == 42 and "unchanged" in doc.pages[0].text for doc in data["docs"].values())
    assert sum(group["measured_calls"] for group in summary["groups"]) == 96
    with pytest.raises(ValueError, match="not empty"):
        await execute(data)
    data["output"] = data["output"].with_name("another-run")
    with pytest.raises(ValueError, match="claimed"):
        await execute(data)
    assert len(data["calls"]) == 100


@pytest.mark.parametrize("reason", ["blocked", "budget", "missing_warmup"])
async def test_blocked_admission_constructs_no_clients(prepared_run, reason):
    data = prepared_run
    if reason == "blocked":
        data["receipt"]["status"] = "blocked"
    elif reason == "budget":
        data["config"]["budget_usd"] = .0001
    else:
        data["receipt"]["items"]["classify-0"]["status"] = "error"
    summary = await execute(data)
    manifest, rows, events = files(data)
    assert summary["run_status"] == manifest["status"] == "blocked"
    assert not data["created"] and not data["calls"] and not data["claims"] and not events
    assert len(rows) == 100 and all(not row["dispatched"] for row in rows)


async def test_start_is_durable_before_the_provider_and_failed_warmup_stops(prepared_run, monkeypatch):
    data = prepared_run

    async def unavailable(*args, engine, **kwargs):
        manifest, rows, events = files(data)
        assert not rows
        assert events[-1]["reserved_cost_usd"] > 0
        assert events[-1]["observation_id"] == manifest["execution_plan"][0]["observation_id"]
        raise ProviderError("Service unavailable", requests=[RequestRecord(
            provider=engine.name, model=engine.model, task="classify", status="error", error_code="503")])

    monkeypatch.setattr(runner, "aclassify_document", unavailable)
    await execute(data)
    manifest, rows, events = files(data)
    assert manifest["status"] == "stopped"
    assert len(events) == 1
    assert rows[0]["status"] == "error" and rows[0]["usage_unknown"]
    assert manifest["budget"]["unknown_cost_reservations_usd"] == events[0]["reserved_cost_usd"]
    assert all(row["status"] == "skipped" for row in rows[1:])


@pytest.mark.parametrize("kind", ["task", "paid", "cancel"])
async def test_deadlines_and_cancellation_retain_unknown_reservation(prepared_run, monkeypatch, kind):
    data = prepared_run
    data["config"]["task_timeout_s"] = .01 if kind == "task" else 1
    data["config"]["paid_timeout_s"] = .01 if kind == "paid" else 5

    async def stalled(*args, **kwargs):
        if kind == "cancel":
            raise asyncio.CancelledError
        await asyncio.sleep(10)

    monkeypatch.setattr(runner, "aclassify_document", stalled)
    await execute(data)
    manifest, rows, events = files(data)
    assert manifest["status"] == ("interrupted" if kind == "cancel" else "stopped")
    assert manifest["stop_reason"]["code"] == {"task": "task_deadline", "paid": "paid_deadline", "cancel": "interrupted"}[kind]
    assert len(events) == 1
    assert rows[0]["usage_unknown"] is True and rows[0]["request_count_complete"] is False
    assert rows[0]["requests"] == []
    assert manifest["budget"]["unknown_cost_reservations_usd"] == events[0]["reserved_cost_usd"]
    assert sum(row["dispatched"] for row in rows) == 1
    assert (data["output"] / "report.md").is_file()


async def test_returned_invalid_result_counts_as_failure_without_retry(prepared_run, monkeypatch):
    data = prepared_run
    calls = 0

    async def invalid_after_warmup(parsed, rules, *, engine, **kwargs):
        nonlocal calls
        calls += 1
        if not parsed.source_name.endswith("-0.pdf"):
            raise ProviderError("Invalid model result", requests=[RequestRecord(
                provider=engine.name, model=engine.model, task="classify", status="invalid",
                cost_usd=.002, cost_status="estimated")])
        return await data["decision"](parsed, rules, engine=engine, **kwargs)

    monkeypatch.setattr(runner, "aclassify_document", invalid_after_warmup)
    await execute(data)
    manifest, rows, events = files(data)
    assert manifest["status"] == "complete"
    assert calls == 82 and len(events) == 100
    assert sum(row["status"] == "error" for row in rows) == 80
    assert all(row["requests"][0]["cost_usd"] == .002 for row in rows if row["status"] == "error")
    assert manifest["budget"]["known_cost_usd"] == pytest.approx(.18)


async def test_preparation_errors_remain_in_schedule_without_dispatch(prepared_run):
    data = prepared_run
    data["receipt"]["items"]["classify-1"]["status"] = "error"
    data["receipt"]["items"]["split-1"]["engine_preflight"]["jev"]["status"] = "error"
    await execute(data)
    manifest, rows, events = files(data)
    assert manifest["status"] == "complete"
    assert len(rows) == 100 and len(events) == 97
    skipped = [row for row in rows if row["status"] == "skipped"]
    assert [row["skip_reason"] for row in skipped].count("preparation_error") == 2
    assert [row["skip_reason"] for row in skipped].count("context_preflight_error") == 1
    assert all(row["wall_ms"] is None and not row["usage_unknown"] for row in skipped)


async def test_budget_denial_stops_next_dispatch(prepared_run, monkeypatch):
    data = prepared_run
    original = runner.Budget.reserve
    count = 0

    async def limited(self, amount):
        nonlocal count
        count += 1
        return await original(self, amount) if count <= 4 else False

    monkeypatch.setattr(runner.Budget, "reserve", limited)
    await execute(data)
    manifest, rows, events = files(data)
    assert manifest["stop_reason"]["code"] == "budget_stop"
    assert len(events) == 4
    assert sum(row["dispatched"] for row in rows) == 4
    assert all(row["skip_reason"] == "budget_stop" for row in rows if not row["dispatched"])


async def test_cleanup_failure_cannot_prevent_a_report(prepared_run, monkeypatch):
    data = prepared_run

    async def failed_close(self):
        raise RuntimeError("secret provider body must never be printed")

    monkeypatch.setattr(runner.JevEngine, "aclose", failed_close)
    await execute(data)
    manifest, rows, _ = files(data)
    assert len(rows) == 100
    assert manifest["status"] == "stopped"
    assert manifest["stop_reason"]["code"] == "cleanup_failure"
    assert len(manifest["cleanup_errors"]) == 2
    assert "secret provider" not in (data["output"] / "manifest.json").read_text()
    assert (data["output"] / "summary.json").is_file()


async def test_client_initialization_failure_closes_prior_client(prepared_run, monkeypatch):
    data = prepared_run

    def no_openai(**kwargs):
        raise ProviderError("Missing credentials")

    monkeypatch.setattr(runner, "OpenAIEngine", no_openai)
    await execute(data)
    manifest, rows, events = files(data)
    assert len(data["created"]) == 1 and data["created"][0].closed
    assert manifest["status"] == "stopped" and not events
    assert len(rows) == 100 and all(not row["dispatched"] for row in rows)


async def test_missing_receipt_and_changed_matrix_never_create_clients(prepared_run):
    data = prepared_run
    with pytest.raises(ValueError, match="--prepared"):
        await runner.run(data["config"], data["dataset"], data["output"])
    data["receipt"]["execution_plan"][0]["engine"] = "different"
    with pytest.raises(ValueError, match="execution plan"):
        await execute(data)
    assert not data["created"] and not data["calls"]


async def test_terminal_write_failure_never_becomes_undispatched(prepared_run, monkeypatch):
    data = prepared_run
    append = runner._append_jsonl
    failed = False

    def fail_one_terminal(path, value):
        nonlocal failed
        if path.name == "raw.jsonl" and value.get("dispatched") and not failed:
            failed = True
            raise OSError("Simulated write failure")
        append(path, value)

    monkeypatch.setattr(runner, "_append_jsonl", fail_one_terminal)
    await execute(data)
    manifest, rows, events = files(data)
    assert len(events) == 1 and len(rows) == 99
    assert manifest["missing_terminal_count"] == 1
    assert events[0]["observation_id"] not in {row["observation_id"] for row in rows}
    assert manifest["status"] == "stopped"
    summary = json.loads((data["output"] / "summary.json").read_text())
    assert sum(group["completed_unique"] for group in summary["groups"]) == 0


async def test_cleanup_time_is_excluded_from_paid_and_measured_intervals(prepared_run, monkeypatch):
    data = prepared_run
    data["config"]["cleanup_timeout_s"] = .2

    async def delayed_close(self):
        await asyncio.sleep(.06)
        self.closed = True

    monkeypatch.setattr(runner.JevEngine, "aclose", delayed_close)
    await execute(data)
    manifest, _, _ = files(data)
    assert manifest["elapsed_seconds"] - manifest["paid_elapsed_seconds"] >= .05
    assert manifest["status"] == "complete"


@pytest.mark.parametrize("error_code", ["401", "403", "404", "429", "503", "APITimeoutError", "ConnectError"])
async def test_service_failures_after_warmups_stop_all_subsequent_dispatch(prepared_run, monkeypatch, error_code):
    data = prepared_run
    original = data["decision"]
    attempted = 0

    async def unreliable(parsed, rules, *, engine, **kwargs):
        nonlocal attempted
        attempted += 1
        if not parsed.source_name.endswith("-0.pdf"):
            raise ProviderError("Provider operation failed", requests=[RequestRecord(
                provider=engine.name, model=engine.model, task="split", status="error", error_code=error_code)])
        return await original(parsed, rules, engine=engine, **kwargs)

    monkeypatch.setattr(runner, "aclassify_document", unreliable)
    monkeypatch.setattr(runner, "asplit_document", unreliable)
    await execute(data)
    manifest, rows, events = files(data)
    assert attempted == 5 and len(events) == 5
    assert manifest["stop_reason"]["code"] == "service_failure"
    assert sum(row["dispatched"] for row in rows) == 5


async def test_remote_context_rejection_is_scored_without_global_service_stop(prepared_run, monkeypatch):
    from jev_docs.errors import ContextLimitError

    data = prepared_run
    original = data["decision"]

    async def rejected(parsed, rules, *, engine, **kwargs):
        if not parsed.source_name.endswith("-0.pdf"):
            raise ContextLimitError("Prepared input exceeded provider context", requests=[RequestRecord(
                provider=engine.name, model=engine.model, task="split", status="error", error_code="413",
                cost_usd=0, cost_status="reported")])
        return await original(parsed, rules, engine=engine, **kwargs)

    monkeypatch.setattr(runner, "asplit_document", rejected)
    await execute(data)
    manifest, rows, events = files(data)
    assert manifest["status"] == "complete"
    assert len(events) == 100 and sum(row["status"] == "error" for row in rows) == 16


def test_cli_prepare_is_separate_from_paid_execution(prepared_run, monkeypatch):
    import sys

    data = prepared_run
    config_path = data["output"].with_suffix(".yaml")
    config_path.write_text(json.dumps(data["config"]))
    monkeypatch.setattr(runner, "load_datasets", lambda *args, **kwargs: data["dataset"])
    prepared = []
    monkeypatch.setattr(prepare, "prepare_corpus", lambda *args, **kwargs: prepared.append(args) or data["receipt"])
    monkeypatch.setattr(sys, "argv", ["benchmark", "--config", str(config_path), "--prepare-only", "--output", str(data["output"])])
    runner.main()
    assert len(prepared) == 1 and not data["created"] and not data["claims"]


def test_cli_rejects_prohibited_overrides_before_loading_data(monkeypatch):
    import sys

    config_path = runner.ROOT / "benchmarks/configs/real-small-v1.yaml"
    monkeypatch.setattr(runner, "load_datasets", lambda *args, **kwargs: pytest.fail("Invalid profile reached dataset loading"))
    monkeypatch.setattr(sys, "argv", ["benchmark", "--config", str(config_path), "--dry-run", "--repeats", "2"])
    with pytest.raises(ValueError, match="repeats"):
        runner.main()


def test_cli_requires_receipt_before_loading_data(monkeypatch):
    import sys

    config_path = runner.ROOT / "benchmarks/configs/real-small-v1.yaml"
    monkeypatch.setattr(runner, "load_datasets", lambda *args, **kwargs: pytest.fail("Missing receipt reached dataset loading"))
    monkeypatch.setattr(sys, "argv", ["benchmark", "--config", str(config_path)])
    with pytest.raises(SystemExit) as error:
        runner.main()
    assert error.value.code == 2

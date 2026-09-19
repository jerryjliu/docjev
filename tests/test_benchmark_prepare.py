"""Local preparation admission and worker cleanup; no decision providers."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from benchmarks import prepare
from jev_docs.cache import digest_file
from jev_docs.schemas import Page, ParsedDocument, RunMetrics


@pytest.fixture
def local_corpus(tmp_path, monkeypatch):
    """Fake source bytes exercise receipts; corpus authenticity has separate tests."""
    config = {
        "experiment_kind": prepare.PROFILE, "repeats": 1, "warmups": 1, "warmup_policy": "dev",
        "concurrency": 1, "scope": "decision", "ocr": "liteparse", "budget_usd": 2,
        "jev_model": "jev-1.13.0", "baseline_model": "gpt-5.6-luna", "seed": 20260919,
        "max_retries": 0, "context_recovery": False, "window_size": 8,
        "min_probability": .7, "boundary_threshold": .5, **prepare.LIMITS,
        "tasks": {task: {"manifest": f"{prepare.CORPUS}/manifests/{task}.json",
                         "rules": f"{prepare.CORPUS}/rules/{task}.yaml"} for task in ("classify", "split")},
    }
    datasets = {"classify": [], "split": []}

    def item(name, task, partition, pages=1, **extra):
        path = tmp_path / prepare.CORPUS / "files" / f"{name}.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"Fake source identity {name}".encode())
        return {"id": name, "path": str(path.relative_to(tmp_path)), "sha256": digest_file(path),
                "split": partition, "page_count": pages, **extra}

    originals = []
    for index in range(40):
        label = sorted(prepare.LABELS)[index // 8]
        originals.append(item(f"e{index:03}", "classify", "test", category=label, source_ids=[f"e{index:03}"]))
    datasets["classify"] = [item("warmup-classify", "classify", "dev", category="other"), *originals]
    packets = []
    for index in range(8):
        group = originals[index * 5:(index + 1) * 5]
        packets.append(item(f"p{index:03}", "split", "test", pages=5,
                            source_ids=[source["id"] for source in group],
                            segments=[{"category": source["category"], "pages": [i + 1]} for i, source in enumerate(group)]))
    datasets["split"] = [item("warmup-split", "split", "dev", source_ids=["old-demo"],
                              segments=[{"category": "other", "pages": [1]}]), *packets]
    for task, paths in config["tasks"].items():
        manifest = tmp_path / paths["manifest"]
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(datasets[task]))
        rules = tmp_path / paths["rules"]
        rules.parent.mkdir(parents=True, exist_ok=True)
        rules.write_text((prepare.ROOT / f"examples/real/{task}/rules.yaml").read_text())
    (tmp_path / prepare.CORPUS / "FREEZE.json").write_text('{"fixture": true}')
    monkeypatch.setattr(prepare, "_verify_corpus", lambda root: {"fixture": True})

    def parse(source, config, root, timeout):
        canonical = root / ".jev-docs/cache/canonical" / f"{source['sha256']}.pdf"
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_bytes((root / source["path"]).read_bytes())
        return ParsedDocument(source_name=Path(source["path"]).name, source_sha256=source["sha256"],
                              canonical_path=str(canonical), canonical_sha256=digest_file(canonical),
                              page_count=source["page_count"],
                              pages=[Page(number=i, text=f"Complete source page {i} with useful content")
                                     for i in range(1, source["page_count"] + 1)],
                              parser=prepare.parser_info(),
                              metrics=RunMetrics(ocr_ms=12, total_ms=15, ocr_cost_usd=0, ocr_cost_status="not_applicable"))

    monkeypatch.setattr(prepare, "_parse_in_subprocess", parse)
    return config, datasets, tmp_path, parse


def test_all_inputs_are_prepared_before_clients_and_shared_without_ocr(local_corpus, monkeypatch):
    config, datasets, root, _ = local_corpus

    def forbidden(*args, **kwargs):
        raise AssertionError("Inference client or second OCR must not be constructed")

    monkeypatch.setattr(prepare.JevEngine, "__init__", forbidden)
    monkeypatch.setattr(prepare.OpenAIEngine, "__init__", forbidden)
    output = root / "preflight"
    receipt = prepare.prepare_corpus(config, datasets, output, root=root)
    assert receipt["status"] == "ready" and receipt["remote_calls"] == 0
    assert len(receipt["items"]) == 50
    assert len(receipt["execution_plan"]) == 100
    assert sum(row["phase"] == "warmup" for row in receipt["execution_plan"]) == 4
    assert receipt["budget_estimate"]["dispatchable_task_calls"] == 100
    assert str(root) not in (output / "preparation.json").read_text()
    assert all(entry["preparation_metrics"]["ocr_ms"] == 12 for entry in receipt["items"].values())
    monkeypatch.setattr(prepare, "_parse_in_subprocess", forbidden)
    _, docs = prepare.load_prepared(config, datasets, output / "preparation.json", root=root)
    assert len(docs) == 50
    assert all(doc.metrics.ocr_ms == 0 and doc.metrics.requests == [] for doc in docs.values())
    assert all(doc.metrics.ocr_cost_usd == 0 for doc in docs.values())


@pytest.mark.parametrize("field,value", [("budget_usd", 2.01), ("repeats", 2), ("warmups", 0),
    ("concurrency", 4), ("ocr", "llamaparse"), ("context_recovery", True),
    ("baseline_model", "another-model"), ("pilot_limit_per_task", 1),
    ("paid_timeout_s", 301), ("task_timeout_s", float("nan")), ("ocr_timeout_s", 0)])
def test_scope_overrides_fail_locally(local_corpus, field, value):
    config, datasets, root, _ = local_corpus
    config[field] = value
    with pytest.raises(ValueError):
        prepare.prepare_corpus(config, datasets, root / "not-created", root=root)
    assert not (root / "not-created").exists()


def test_duplicate_ids_and_missing_manifest_rows_fail_before_ocr(local_corpus):
    config, datasets, root, _ = local_corpus
    datasets["split"][0]["id"] = datasets["classify"][0]["id"]
    with pytest.raises(ValueError, match="unique"):
        prepare.validate_profile(config, datasets, root=root)
    datasets["split"][0]["id"] = "warmup-split"
    datasets["classify"].pop()
    with pytest.raises(ValueError, match="complete frozen manifest"):
        prepare.validate_profile(config, datasets, root=root)


def test_manifest_can_store_development_rows_after_test_rows(local_corpus):
    config, datasets, root, _ = local_corpus
    for task, items in datasets.items():
        (root / config["tasks"][task]["manifest"]).write_text(json.dumps([*items[1:], items[0]]))
    prepare.validate_profile(config, datasets, root=root)


def test_actual_text_budget_blocks_without_clients(local_corpus, monkeypatch):
    config, datasets, root, _ = local_corpus
    config["budget_usd"] = 0.00001
    monkeypatch.setattr(prepare.JevEngine, "__init__", lambda *a, **kw: pytest.fail("No inference"))
    receipt = prepare.prepare_corpus(config, datasets, root / "blocked", root=root)
    assert receipt["status"] == "blocked"
    assert receipt["blockers"] == ["estimated_budget_exceeded"]
    loaded, _ = prepare.load_prepared(config, datasets, root / "blocked/preparation.json", root=root)
    assert loaded["status"] == "blocked"
    with pytest.raises(ValueError, match="ready"):
        prepare.claim_prepared(root / "blocked/preparation.json", receipt, root / "attempt", root=root)


@pytest.mark.parametrize("target", ["receipt", "artifact", "canonical", "source", "rules", "config"])
def test_prepared_identity_changes_fail_without_reparsing(local_corpus, monkeypatch, target):
    config, datasets, root, _ = local_corpus
    receipt = prepare.prepare_corpus(config, datasets, root / "preflight", root=root)
    receipt_path = root / "preflight/preparation.json"
    entry = receipt["items"]["e000"]
    if target == "receipt":
        data = json.loads(receipt_path.read_text())
        data["status"] = "blocked"
        receipt_path.write_text(json.dumps(data))
    elif target == "artifact":
        (root / entry["artifact"]).write_text('{}')
    elif target == "canonical":
        artifact = json.loads((root / entry["artifact"]).read_text())
        Path(artifact["canonical_path"]).write_bytes(b"changed")
    elif target == "source":
        (root / datasets["classify"][1]["path"]).write_bytes(b"changed")
    elif target == "rules":
        path = root / config["tasks"]["classify"]["rules"]
        path.write_text(path.read_text() + "\n# Changed rules\n")
    else:
        config["min_probability"] = .9
    monkeypatch.setattr(prepare, "_parse_in_subprocess", lambda *a: pytest.fail("No hidden reparse"))
    with pytest.raises(ValueError):
        prepare.load_prepared(config, datasets, receipt_path, root=root)


def test_receipt_only_permits_one_paid_attempt(local_corpus):
    config, datasets, root, _ = local_corpus
    receipt = prepare.prepare_corpus(config, datasets, root / "preflight", root=root)
    path = root / "preflight/preparation.json"
    prepare.claim_prepared(path, receipt, root / "run01", root=root)
    with pytest.raises(ValueError, match="already has an execution attempt"):
        prepare.claim_prepared(path, receipt, root / "different-name", root=root)


def test_failed_test_ocr_stays_in_receipt_and_warmup_failure_blocks(local_corpus, monkeypatch):
    config, datasets, root, parse = local_corpus

    def fail_test(item, *args):
        if item["id"] == "e000":
            raise ValueError("private provider or path details must not be published")
        return parse(item, *args)

    monkeypatch.setattr(prepare, "_parse_in_subprocess", fail_test)
    receipt = prepare.prepare_corpus(config, datasets, root / "test-error", root=root)
    assert receipt["status"] == "ready"
    assert receipt["items"]["e000"]["status"] == "error"
    assert receipt["budget_estimate"]["planned_task_calls"] == 100
    assert receipt["budget_estimate"]["dispatchable_task_calls"] == 98
    assert "private provider" not in json.dumps(receipt)

    def fail_warmup(item, *args):
        if item["split"] == "dev":
            raise ValueError("OCR failure")
        return parse(item, *args)

    monkeypatch.setattr(prepare, "_parse_in_subprocess", fail_warmup)
    receipt = prepare.prepare_corpus(config, datasets, root / "warmup-error", root=root)
    assert receipt["status"] == "blocked"
    assert len(receipt["items"]) == 50
    assert all(reason.startswith("warmup_preparation_failed:") for reason in receipt["blockers"])


def test_local_context_failure_records_unusable_engine_without_truncation(local_corpus, monkeypatch):
    config, datasets, root, parse = local_corpus

    def oversized(item, *args):
        document = parse(item, *args)
        if item["id"] == "e000":
            document.pages[0].text = "x" * 600_000
        return document

    monkeypatch.setattr(prepare, "_parse_in_subprocess", oversized)
    receipt = prepare.prepare_corpus(config, datasets, root / "large", root=root)
    entry = receipt["items"]["e000"]
    assert entry["text_bytes"] == 600_000
    assert all(value["status"] == "error" for value in entry["engine_preflight"].values())
    assert receipt["status"] == "ready"
    assert receipt["budget_estimate"]["dispatchable_task_calls"] == 98


def test_cache_hit_reports_actual_preparation_and_resets_decision_costs(local_corpus, monkeypatch):
    config, datasets, root, parse = local_corpus

    def cached(item, *args):
        document = parse(item, *args)
        document.metrics = RunMetrics(ocr_cache_hit=True, conversion_ms=2, total_ms=2,
                                      ocr_cost_usd=0, ocr_cost_status="not_applicable")
        return document

    monkeypatch.setattr(prepare, "_parse_in_subprocess", cached)
    receipt = prepare.prepare_corpus(config, datasets, root / "cached", root=root)
    assert all(entry["cache_hit"] and entry["preparation_metrics"]["ocr_ms"] == 0
               for entry in receipt["items"].values())


def test_stalled_process_is_killed_and_reaped(tmp_path):
    pid_path = tmp_path / "pid"
    code = "import os,signal,sys,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); open(sys.argv[1],'w').write(str(os.getpid())); time.sleep(60)"
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        prepare._bounded_process([sys.executable, "-c", code, str(pid_path)], timeout=.3, cwd=tmp_path)
    assert time.monotonic() - started < 4
    pid = int(pid_path.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_total_preparation_deadline_stops_remaining_ocr(local_corpus, monkeypatch):
    config, datasets, root, parse = local_corpus
    config["preparation_timeout_s"] = .01
    calls = []

    def slow(item, *args):
        calls.append(item["id"])
        time.sleep(.02)
        return parse(item, *args)

    monkeypatch.setattr(prepare, "_parse_in_subprocess", slow)
    receipt = prepare.prepare_corpus(config, datasets, root / "deadline", root=root)
    assert receipt["status"] == "blocked"
    assert "preparation_deadline" in receipt["blockers"]
    assert len(calls) <= 1
    assert len(receipt["items"]) == 50


def test_final_identity_check_cannot_overrun_deadline_and_admit_payment(local_corpus, monkeypatch):
    config, datasets, root, _ = local_corpus
    clock = [0.0]
    original = prepare._identity
    checks = []

    def identity(*args):
        checks.append(True)
        if len(checks) == 2:
            clock[0] = config["preparation_timeout_s"] + 1
        return original(*args)

    monkeypatch.setattr(prepare.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(prepare, "_identity", identity)
    receipt = prepare.prepare_corpus(config, datasets, root / "final-deadline", root=root)
    assert receipt["status"] == "blocked"
    assert receipt["blockers"] == ["preparation_deadline"]
    assert receipt["budget_estimate"]["dispatchable_task_calls"] == 100
    assert all(item["status"] == "ok" for item in receipt["items"].values())

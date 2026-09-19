"""Run frozen-data, budgeted comparisons. No API calls occur in --dry-run."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import random
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from jev_docs.cache import digest_file
from jev_docs.classify import aclassify_document
from jev_docs.documents import parse_document
from jev_docs.engines.jev import JevEngine
from jev_docs.engines.openai import OpenAIEngine
from jev_docs.errors import ContextLimitError, JevDocsError
from jev_docs.rules import load_rules
from jev_docs.schemas import ParsedDocument, RuleSet, RunMetrics
from jev_docs.split import asplit_document

from .report import write_report

ROOT = Path(__file__).resolve().parents[1]
REAL_PROFILE = "real-document-accuracy-pilot"


class Budget:
    """Conservatively reserve estimated cost before dispatch; retain unknown charges."""

    def __init__(self, limit: float):
        self.limit = limit
        self.committed = 0.0
        self.known = 0.0
        self.unknown_reserved = 0.0
        self.lock = asyncio.Lock()

    async def reserve(self, amount: float) -> bool:
        async with self.lock:
            if self.committed + amount > self.limit:
                return False
            self.committed += amount
            return True

    async def settle(self, reserved: float, requests: list[dict], *, dispatched: bool,
                     usage_unknown: bool = False) -> None:
        known = sum(record["cost_usd"] for record in requests if record.get("cost_usd") is not None)
        unknown = dispatched and (usage_unknown or not requests or any(record.get("cost_usd") is None for record in requests))
        async with self.lock:
            self.known += known
            retained = max(reserved, known) if unknown else known
            self.committed += retained - reserved
            if unknown:
                self.unknown_reserved += max(0, retained - known)

    def public(self) -> dict:
        return {"limit_usd": self.limit, "known_cost_usd": self.known,
                "unknown_cost_reservations_usd": self.unknown_reserved,
                "committed_usd": self.committed, "is_provider_billing_cap": False}


def load_config(path: Path) -> dict:
    config = yaml.safe_load(path.read_text())
    validate_config(config)
    return config


def validate_config(config: dict) -> None:
    if config.get("repeats", 0) < 1 or config.get("warmups", -1) < 0:
        raise ValueError("repeats must be positive and warmups nonnegative")
    if config.get("concurrency") not in (1, 4):
        raise ValueError("Use concurrency 1 (primary) or 4 (separate throughput condition)")
    if config.get("scope") not in ("decision", "end-to-end"):
        raise ValueError("scope must be decision or end-to-end")
    if config.get("max_retries", 0) != 0:
        raise ValueError("Published benchmark protocol disables retries")
    if config.get("budget_usd", 0) <= 0:
        raise ValueError("budget_usd must be positive")
    if config.get("baseline_model") not in ("gpt-5.6-luna", "gpt-4o-mini", "gpt-4o-mini-2024-07-18"):
        raise ValueError("Add a reviewed price/reservation entry before benchmarking another baseline")
    if config.get("warmup_policy") == "reuse-demo-sources" and config.get("experiment_kind") != "demonstration":
        raise ValueError("Reusing measured sources as warmups is limited to explicitly labeled demonstrations")


def load_datasets(config: dict, *, limit: int | None = None) -> dict[str, list[dict]]:
    datasets = {}
    for task, settings in config["tasks"].items():
        data = json.loads((ROOT / settings["manifest"]).read_text())
        for item in data:
            if digest_file(ROOT / item["path"]) != item["sha256"]:
                raise ValueError(f"Dataset hash mismatch for {item['id']}; freeze inputs before evaluation")
        dev = [item for item in data if item["split"] == "dev"]
        test = [item for item in data if item["split"] == "test"]
        if limit:
            test = test[:limit]
        datasets[task] = [*dev, *test]
    return datasets


def warmup_items(config: dict, items: list[dict]) -> list[dict]:
    # A demo pilot has no held-out accuracy claim; source reuse is explicit.
    split = "test" if config.get("warmup_policy") == "reuse-demo-sources" else "dev"
    return [item for item in items if item["split"] == split][:config["warmups"]]


def build_execution_plan(config: dict, datasets: dict[str, list[dict]]) -> list[dict]:
    """Freeze order and stable identities before OCR or model client creation."""
    randomizer = random.Random(config["seed"])
    plan: list[dict] = []

    def append_pair(task: str, item: dict, repeat: int, phase: str) -> None:
        names = ["jev", "openai"]
        randomizer.shuffle(names)
        for name in names:
            source_id = item["id"]
            plan.append({
                "observation_id": f"{phase}:{task}:{source_id}:{name}:{repeat}",
                "task": task, "engine": name,
                "model": config["jev_model" if name == "jev" else "baseline_model"],
                "scope": config["scope"], "concurrency": config["concurrency"],
                "source_id": source_id, "repeat": repeat, "phase": phase,
            })

    for task, items in datasets.items():
        for item in warmup_items(config, items):
            append_pair(task, item, -1, "warmup")
    for repeat in range(config["repeats"]):
        jobs = [(task, item) for task, items in datasets.items()
                for item in items if item["split"] == "test"]
        randomizer.shuffle(jobs)
        for task, item in jobs:
            append_pair(task, item, repeat, "measured")
    return plan


def reservation(engine: str, item: dict, document: ParsedDocument | None,
                config: dict, rules_text: str) -> float:
    pages = item["page_count"]
    if engine == "jev":
        windows = max(1, math.ceil(pages / config.get("window_size", 8)))
        if document is not None and config.get("experiment_kind") == REAL_PROFILE:
            from jev_docs.engines.jev import JevEngine as JevAdapter

            task = "split" if "segments" in item else "classify"
            actual = JevAdapter.preflight(document, RuleSet.model_validate(yaml.safe_load(rules_text)),
                                         task, window_size=config.get("window_size", 8))
            if actual["request_count"] == 0:
                return 0.0
            windows = max(windows, actual["request_count"])
        # Published maximum 64k input tokens per call; allow window-size recovery.
        decision = windows * 64_000 * 0.042 / 1_000_000 * 2
    else:
        # One UTF-8 byte per token plus a generous fixed instruction/schema margin.
        content_bytes = sum(len(page.text.encode()) for page in document.pages) if document else pages * 12_000
        input_bound = content_bytes + len(rules_text.encode()) * 2 + 12_000 + pages * 160
        # Includes possible input cache-write premium. Selected baseline prices capped above known small defaults.
        decision = input_bound * 0.25 / 1_000_000 + max(128, pages * 45 + 100) * 1.2 / 1_000_000
    if config["scope"] == "end-to-end" and config["ocr"] == "llamaparse":
        decision += pages * {"cost-effective": 3, "cost_effective": 3, "agentic": 10,
                             "agentic-plus": 45, "agentic_plus": 45}[config["tier"]] * 0.00125
    return decision


def dry_run(config: dict, datasets: dict[str, list[dict]]) -> dict:
    tasks = {}
    reserved = 0.0
    for task, items in datasets.items():
        test = [item for item in items if item["split"] == "test"]
        dev = warmup_items(config, items)
        rules_text = (ROOT / config["tasks"][task]["rules"]).read_text()
        paid = config["repeats"] * test + dev
        estimate = sum(reservation(engine, item, None, config, rules_text)
                       for item in paid for engine in ("jev", "openai"))
        reserved += estimate
        tasks[task] = {"test_documents": len(test), "test_pages": sum(item["page_count"] for item in test),
                       "warmups_per_engine": len(dev), "measured_task_calls": len(test) * config["repeats"] * 2,
                       "estimated_upper_reservations_usd": estimate}
        if config["scope"] == "decision" and config["ocr"] == "llamaparse":
            tier = config["tier"].replace("-", "_")
            reserved += sum(item["page_count"] for item in [*dev, *test]) * {"cost_effective": 3, "agentic": 10, "agentic_plus": 45}[tier] * 0.00125
    plan = build_execution_plan(config, datasets)
    return {"dry_run": True, "remote_calls": 0, "tasks": tasks, "budget_usd": config["budget_usd"],
            "planned_measured_task_invocations": sum(row["phase"] == "measured" for row in plan),
            "planned_warmup_task_invocations": sum(row["phase"] == "warmup" for row in plan),
            "estimated_upper_reservations_usd": reserved, "within_estimated_budget": reserved <= config["budget_usd"],
            "note": "Preflight estimate assumes 12,000 OCR bytes/page; real dispatch reservations use actual text bytes. It is not a provider billing cap."}


async def _run_legacy(config: dict, datasets: dict[str, list[dict]], output: Path) -> dict:
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory is not empty; choose a new run directory")
    output.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC).isoformat()
    source_files = [*list((ROOT / "src/jev_docs/engines").glob("*.py")),
                    ROOT / "src/jev_docs/windows.py", ROOT / "src/jev_docs/split.py",
                    ROOT / "src/jev_docs/classify.py", ROOT / "benchmarks/pricing.json"]
    packages: dict[str, str | None] = {}
    for name in ("docjev", "liteparse", "llama-cloud", "typesafe-sdk", "openai", "pypdf"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    manifest: dict[str, Any] = {"schema_version": "1", "run_id": output.name, "started_at": started_at,
                               "status": "running", "config": config, "datasets": datasets,
                               "demo_set": config.get("demo_set", "synthetic"),
                               "experiment_kind": config.get("experiment_kind", "heldout-synthetic-benchmark"),
                               "system": {"os": platform.system(), "release": platform.release(),
                                          "machine": platform.machine(), "python": platform.python_version()},
                               "packages": packages, "source_hashes": {str(path.relative_to(ROOT)): digest_file(path) for path in source_files},
                               "input_manifest_hashes": {task: digest_file(ROOT / settings["manifest"]) for task, settings in config["tasks"].items()},
                               "rules_hashes": {task: digest_file(ROOT / settings["rules"]) for task, settings in config["tasks"].items()},
                               "lock_sha256": digest_file(ROOT / "uv.lock"), "parsed_artifacts": {},
                               "protocol": {"provider_order": "seeded paired randomization", "quality_pass": 0,
                                            "provider_cache_control": "not controlled for decision engines",
                                            "client_state": "reused after excluded dev warmups",
                                            "comparison": "practical task implementations",
                                            "geographic_region": "not inferred", "process_cold_measured": False}}
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    raw_path = output / "raw.jsonl"
    raw_path.touch()
    budget = Budget(config["budget_usd"])
    engines: dict[str, Any] = {"jev": JevEngine(model=config["jev_model"], max_retries=0, window_size=config.get("window_size", 8)),
                               "openai": OpenAIEngine(model=config["baseline_model"])}
    rules = {task: load_rules(ROOT / settings["rules"]) for task, settings in config["tasks"].items()}
    documents: dict[str, ParsedDocument | Exception] = {}
    semaphore = asyncio.Semaphore(config["concurrency"])
    completed_count = 0
    randomizer = random.Random(config["seed"])
    parsed_root = ROOT / ".jev-docs" / "benchmark-parsed" / output.name
    parsed_root.mkdir(parents=True, exist_ok=True)
    task_started = time.perf_counter()

    async def prepare(item: dict) -> ParsedDocument:
        if item["id"] not in documents:
            ocr_reservation = 0.0
            ocr_records: list[dict] = []
            ocr_dispatched = False
            try:
                if config["ocr"] == "llamaparse":
                    tier = config["tier"].replace("-", "_")
                    ocr_reservation = item["page_count"] * {"cost_effective": 3, "agentic": 10, "agentic_plus": 45}[tier] * 0.00125
                    if not await budget.reserve(ocr_reservation):
                        ocr_reservation = 0
                        raise JevDocsError("Local estimated API budget exhausted before OCR preparation")
                    ocr_dispatched = True
                parsed = await asyncio.to_thread(parse_document, ROOT / item["path"],
                                                 ocr=config["ocr"], tier=config["tier"],
                                                 parser_version=config["parser_version"])
                ocr_records = [record.model_dump() for record in parsed.metrics.requests]
                if parsed.metrics.ocr_cache_hit:
                    ocr_dispatched = False
                if parsed.page_count != item["page_count"]:
                    raise ValueError("Canonical page count differs from frozen ground truth")
                if item.get("sha256") and parsed.source_sha256 != item["sha256"]:
                    raise JevDocsError("Input bytes changed after the dataset was frozen; no decision was dispatched")
                artifact_text = json.dumps([page.model_dump() for page in parsed.pages], sort_keys=True)
                manifest["parsed_artifacts"][item["id"]] = {
                    "pages_sha256": hashlib.sha256(artifact_text.encode()).hexdigest(),
                    "canonical_sha256": parsed.canonical_sha256, "parser": parsed.parser.model_dump(),
                    "preparation_metrics": parsed.metrics.model_dump()}
                (parsed_root / f"{item['id']}.json").write_text(parsed.model_dump_json(indent=2))
                # OCR preparation happened once; replayed decisions must not re-charge it.
                parsed.metrics = RunMetrics(ocr_cache_hit=True, ocr_cost_usd=0, ocr_cost_status="not_applicable")
                documents[item["id"]] = parsed
            except Exception as exc:
                documents[item["id"]] = exc
                ocr_records = [record.model_dump() for record in getattr(exc, "requests", [])]
            finally:
                if ocr_reservation:
                    await budget.settle(ocr_reservation, ocr_records, dispatched=ocr_dispatched)
        value = documents[item["id"]]
        if isinstance(value, Exception):
            raise value
        return value

    async def execute(task: str, item: dict, engine_name: str, repeat: int, phase: str) -> None:
        nonlocal completed_count
        async with semaphore:
            row: dict[str, Any] = {"task": task, "id": item["id"], "engine": engine_name,
                                   "model": engines[engine_name].model, "repeat": repeat, "phase": phase,
                                   "scope": config["scope"], "concurrency": config["concurrency"],
                                   "started_at": datetime.now(UTC).isoformat(), "status": "error",
                                   "requests": [], "page_count": item["page_count"]}
            start = time.perf_counter()
            reserved = 0.0
            dispatched = False
            result: Any
            try:
                parsed = await prepare(item) if config["scope"] == "decision" else None
                reserved = reservation(engine_name, item, parsed, config, rules[task].model_dump_json())
                if not await budget.reserve(reserved):
                    reserved = 0.0
                    raise JevDocsError("Local estimated API budget exhausted; call was not dispatched")
                row["reserved_cost_usd"] = reserved
                # Start measured time after preparation/reservation: decision and OCR scopes are explicit.
                start = time.perf_counter()
                dispatched = True
                source = parsed if parsed is not None else ROOT / item["path"]
                options = {"engine": engines[engine_name], "min_probability": config["min_probability"]}
                if parsed is None:
                    options.update(ocr=config["ocr"], tier=config["tier"],
                                   parser_version=config["parser_version"], use_cache=False)
                if task == "classify":
                    result = await aclassify_document(source, rules[task], **options)
                else:
                    result = await asplit_document(source, rules[task], boundary_threshold=config["boundary_threshold"], **options)
                row["result"] = result.model_dump()
                row["requests"] = [record.model_dump() for record in result.metrics.requests]
                row["status"] = "ok"
                if parsed is not None:
                    row["parsed_pages_sha256"] = manifest["parsed_artifacts"][item["id"]]["pages_sha256"]
            except Exception as exc:
                row["error"] = {"type": type(exc).__name__,
                                "message": str(exc) if isinstance(exc, JevDocsError) else "Document or provider operation failed"}
                row["requests"] = [record.model_dump() for record in getattr(exc, "requests", [])]
            finally:
                row["wall_ms"] = (time.perf_counter() - start) * 1000
                row["dispatched"] = dispatched
                if reserved:
                    await budget.settle(reserved, row["requests"], dispatched=dispatched)
                with raw_path.open("a") as stream:
                    stream.write(json.dumps(row) + "\n")
                    stream.flush()
                completed_count += 1
                print(f"{phase} {task} {item['id']} {engine_name}: {row['status']} ({row['wall_ms']:.0f} ms); cost guard ${budget.committed:.4f}", file=sys.stderr, flush=True)
                manifest["budget"] = budget.public()
                manifest["observations_written"] = completed_count
                manifest_path.write_text(json.dumps(manifest, indent=2))

    try:
        for task, items in datasets.items():
            dev = warmup_items(config, items)
            for item in dev:
                names = list(engines)
                randomizer.shuffle(names)
                for name in names:
                    await execute(task, item, name, -1, "warmup")
        # Materialize normalized artifacts before timing and before parallel tasks can race.
        if config["scope"] == "decision":
            for items in datasets.values():
                for item in items:
                    if item["split"] == "test":
                        try:
                            await prepare(item)
                        except Exception:
                            pass  # Every planned measured observation records the OCR failure.
        measurement_start = time.perf_counter()
        for repeat in range(config["repeats"]):
            jobs = [(task, item) for task, items in datasets.items() for item in items if item["split"] == "test"]
            randomizer.shuffle(jobs)
            planned = []
            for task, item in jobs:
                names = list(engines)
                randomizer.shuffle(names)
                for name in names:
                    planned.append((task, item, name, repeat, "measured"))
            if config["concurrency"] == 1:
                for arguments in planned:
                    await execute(*arguments)
            else:
                await asyncio.gather(*(execute(*arguments) for arguments in planned))
        manifest["measured_elapsed_seconds"] = time.perf_counter() - measurement_start
        manifest["status"] = "complete"
    finally:
        await asyncio.gather(*(engine.aclose() for engine in engines.values()))
        manifest["finished_at"] = datetime.now(UTC).isoformat()
        manifest["elapsed_seconds"] = time.perf_counter() - task_started
        manifest["budget"] = budget.public()
        manifest_path.write_text(json.dumps(manifest, indent=2))
    return write_report(output)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _append_jsonl(path: Path, value: dict) -> None:
    with path.open("a") as stream:
        stream.write(json.dumps(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _safe_error(exc: Exception) -> dict:
    return {"type": type(exc).__name__,
            "message": str(exc) if isinstance(exc, JevDocsError) else "Document or provider operation failed"}


def _service_failure(records: list[dict]) -> bool:
    for record in records:
        code = str(record.get("error_code") or "").lower()
        if code.isdigit() and 400 <= int(code) <= 599:
            return True
        if any(word in code for word in ("timeout", "connection", "connecterror", "network", "transport")):
            return True
    return False


async def _run_prepared(config: dict, datasets: dict[str, list[dict]], output: Path,
                        prepared_path: Path, receipt: dict,
                        documents: dict[str, ParsedDocument]) -> dict:
    """One bounded attempt over a frozen local receipt; never invokes OCR."""
    from .prepare import claim_prepared

    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory is not empty; choose a new run directory")
    plan = build_execution_plan(config, datasets)
    receipt_plan = [{k: v for k, v in row.items() if k != "reserved_cost_usd"}
                    for row in receipt.get("execution_plan", [])]
    if receipt_plan != plan:
        raise ValueError("Prepared execution plan differs from the frozen configuration")
    items = {item["id"]: item for entries in datasets.values() for item in entries}
    rules = {task: load_rules(ROOT / settings["rules"])
             for task, settings in config["tasks"].items()}
    prepared_items = receipt.get("items", {})
    reservations: dict[str, float] = {}
    admission_error: dict | None = None
    for row in plan:
        source_id, engine = row["source_id"], row["engine"]
        entry = prepared_items.get(source_id, {})
        check = entry.get("engine_preflight", {}).get(engine, {})
        dispatchable = entry.get("status") == "ok" and check.get("status") == "ok"
        if dispatchable:
            if source_id not in documents:
                raise ValueError("Prepared document is missing from the validated receipt")
            reservations[row["observation_id"]] = reservation(
                engine, items[source_id], documents[source_id], config,
                rules[row["task"]].model_dump_json(),
            )
        elif row["phase"] == "warmup":
            admission_error = {"code": "warmup_preparation_failed", "message": "A required warmup could not be prepared."}
    estimate = sum(reservations.values())
    if receipt.get("status") != "ready":
        admission_error = {"code": "preparation_blocked", "message": "The preparation receipt blocks paid execution."}
    if estimate > config["budget_usd"]:
        admission_error = {"code": "preflight_budget", "message": "The full actual-text reservation exceeds the local budget."}

    # Claim once only after validation/admission, before constructing even one client.
    if admission_error is None:
        claim_prepared(prepared_path, receipt, output, root=ROOT)
    output.mkdir(parents=True, exist_ok=True)
    source_paths = sorted({*ROOT.glob("src/jev_docs/**/*.py"),
                           *ROOT.glob("benchmarks/*.py"), ROOT / "benchmarks/pricing.json"})
    packages: dict[str, str | None] = {}
    for name in ("docjev", "liteparse", "typesafe-sdk", "openai", "pypdf"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    budget = Budget(config["budget_usd"])
    manifest = {
        "schema_version": "1", "run_id": output.name, "started_at": _utc_now(),
        "status": "blocked" if admission_error else "running", "stop_reason": admission_error,
        "config": config, "datasets": datasets, "execution_plan": plan,
        "demo_set": config.get("demo_set", "real"), "experiment_kind": REAL_PROFILE,
        "system": {"os": platform.system(), "release": platform.release(),
                   "machine": platform.machine(), "python": platform.python_version()},
        "packages": packages,
        "source_hashes": {str(path.relative_to(ROOT)): digest_file(path) for path in source_paths},
        "input_manifest_hashes": {task: digest_file(ROOT / settings["manifest"])
                                  for task, settings in config["tasks"].items()},
        "rules_hashes": {task: digest_file(ROOT / settings["rules"])
                         for task, settings in config["tasks"].items()},
        "lock_sha256": digest_file(ROOT / "uv.lock"),
        "pricing_snapshot": json.loads((ROOT / "benchmarks/pricing.json").read_text()),
        "preparation_receipt": receipt,
        "parsed_artifacts": {key: value for key, value in prepared_items.items()},
        "estimated_admission_usd": estimate, "budget": budget.public(),
        "protocol": {"provider_order": "seeded paired randomization", "quality_pass": 0,
                     "provider_cache_control": "not controlled for decision engines",
                     "client_state": "reused after excluded dev warmups", "comparison": "practical task implementations",
                     "geographic_region": "not inferred", "process_cold_measured": False,
                     "context_recovery": False, "automatic_resume": False},
    }
    manifest_path, raw_path, events_path = (output / name for name in ("manifest.json", "raw.jsonl", "events.jsonl"))
    _atomic_json(manifest_path, manifest)
    _atomic_json(output / "preparation.json", receipt)
    raw_path.touch()
    events_path.touch()
    engines: dict[str, Any] = {}
    terminal_ids: set[str] = set()
    started_ids: set[str] = set()
    halt = admission_error
    paid_start: float | None = None
    measured_start: float | None = None
    whole_start = time.perf_counter()

    def stop(code: str, message: str, *, interrupted: bool = False) -> None:
        nonlocal halt
        if halt is None:
            halt = {"code": code, "message": message}
            manifest["stop_reason"] = halt
            manifest["status"] = "interrupted" if interrupted else "stopped"

    def new_row(observation: dict) -> dict:
        item = items[observation["source_id"]]
        return {**observation, "id": observation["source_id"], "page_count": item["page_count"],
                "started_at": _utc_now(), "status": "error", "requests": [],
                "dispatched": False, "request_count_complete": True, "usage_unknown": False,
                "wall_ms": None}

    def record(row: dict) -> None:
        if row["observation_id"] in terminal_ids:
            raise ValueError("An observation already has a terminal outcome")
        _append_jsonl(raw_path, row)
        terminal_ids.add(row["observation_id"])
        manifest["observations_written"] = len(terminal_ids)
        manifest["budget"] = budget.public()
        _atomic_json(manifest_path, manifest)
        print(f"{row['phase']} {row['task']} {row['id']} {row['engine']}: {row['status']}; cost guard ${budget.committed:.4f}",
              file=sys.stderr, flush=True)

    def skip(observation: dict, reason: str) -> None:
        row = new_row(observation)
        row.update(status="skipped", skip_reason=reason)
        record(row)

    async def execute(observation: dict) -> None:
        nonlocal measured_start
        row = new_row(observation)
        source_id, engine_name = row["source_id"], row["engine"]
        prepared = prepared_items.get(source_id, {})
        if row["observation_id"] not in reservations:
            reason = "preparation_error" if prepared.get("status") != "ok" else "context_preflight_error"
            skip(observation, reason)
            return
        if halt:
            skip(observation, halt["code"])
            return
        assert paid_start is not None
        remaining = config.get("paid_timeout_s", 300) - (time.perf_counter() - paid_start)
        if remaining <= 0:
            stop("paid_deadline", "The paid-stage deadline was reached.")
            skip(observation, "paid_deadline")
            return
        if row["phase"] == "measured" and measured_start is None:
            measured_start = time.perf_counter()
        reserved = reservations[row["observation_id"]]
        if not await budget.reserve(reserved):
            stop("budget_stop", "The local estimated budget cannot admit the next task.")
            skip(observation, "budget_stop")
            return
        row["reserved_cost_usd"] = reserved
        began: float | None = None
        result: Any
        try:
            event = {**observation, "id": source_id, "event": "dispatch_started",
                     "timestamp": _utc_now(), "reserved_cost_usd": reserved}
            _append_jsonl(events_path, event)
            started_ids.add(row["observation_id"])
            row["dispatched"] = True
            began = time.perf_counter()
            document = documents[source_id].model_copy(deep=True)
            document.metrics = RunMetrics(ocr_cache_hit=True, ocr_cost_usd=0,
                                          ocr_cost_status="not_applicable")
            task_rules = rules[row["task"]].model_copy(deep=True)
            options = {"engine": engines[engine_name], "min_probability": config["min_probability"]}
            async with asyncio.timeout(min(config.get("task_timeout_s", 60), remaining)):
                if row["task"] == "classify":
                    result = await aclassify_document(document, task_rules, **options)
                else:
                    result = await asplit_document(document, task_rules,
                                                   boundary_threshold=config["boundary_threshold"], **options)
            row["result"] = result.model_dump()
            row["requests"] = [request.model_dump() for request in result.metrics.requests]
            row["status"] = "ok"
            row["parsed_pages_sha256"] = prepared.get("pages_sha256")
            row["usage_unknown"] = any(request.get("cost_usd") is None for request in row["requests"])
        except TimeoutError:
            code = "paid_deadline" if time.perf_counter() - paid_start >= config.get("paid_timeout_s", 300) else "task_deadline"
            row.update(error={"type": "TimeoutError", "message": "The bounded decision deadline was reached."},
                       usage_unknown=True, request_count_complete=False, requests=[])
            stop(code, "Decision execution exceeded its configured deadline.")
        except asyncio.CancelledError:
            row.update(error={"type": "CancelledError", "message": "The task was interrupted; provider usage is uncertain."},
                       usage_unknown=row["dispatched"], request_count_complete=not row["dispatched"], requests=[])
            stop("interrupted", "Execution was interrupted; no automatic resume will occur.", interrupted=True)
            raise
        except Exception as exc:
            row["error"] = _safe_error(exc)
            row["requests"] = [request.model_dump() for request in getattr(exc, "requests", [])]
            row["usage_unknown"] = row["dispatched"] and (
                not row["requests"] or any(request.get("cost_usd") is None for request in row["requests"]))
            row["request_count_complete"] = bool(row["requests"]) or not row["dispatched"]
            if not isinstance(exc, ContextLimitError) and _service_failure(row["requests"]):
                stop("service_failure", "A provider reported an authentication, limit, connectivity, or availability failure.")
            elif not isinstance(exc, JevDocsError):
                stop("operation_failure", "An unexpected execution failure stopped the study.")
        finally:
            if began is not None:
                row["wall_ms"] = (time.perf_counter() - began) * 1000
            await budget.settle(reserved, row["requests"], dispatched=row["dispatched"],
                                usage_unknown=row["usage_unknown"])
            if row["phase"] == "warmup" and row["status"] != "ok":
                stop("warmup_failed", "An excluded warmup failed; measured dispatch was stopped.")
            record(row)

    async def close_client(name: str, engine: Any) -> dict | None:
        try:
            async with asyncio.timeout(config.get("cleanup_timeout_s", 5)):
                await engine.aclose()
        except (Exception, asyncio.CancelledError) as exc:
            return {"engine": name, "type": type(exc).__name__, "message": "Client cleanup did not complete normally."}
        return None

    try:
        if halt is None:
            # Setup is outside decision timers; initialization failures cannot leak a client.
            engines["jev"] = JevEngine(model=config["jev_model"], max_retries=0,
                                       window_size=config.get("window_size", 8), context_recovery=False,
                                       timeout=config.get("request_timeout_s", 30))
            engines["openai"] = OpenAIEngine(model=config["baseline_model"],
                                             timeout=config.get("request_timeout_s", 30))
            paid_start = time.perf_counter()
            for observation in plan:
                await execute(observation)
            if halt is None:
                manifest["status"] = "complete"
    except asyncio.CancelledError:
        stop("interrupted", "Execution was interrupted; no automatic resume will occur.", interrupted=True)
    except Exception:
        stop("initialization_or_recording_failure", "Provider setup or evidence recording failed; no more work was dispatched.")
    finally:
        dispatch_end = time.perf_counter()
        # Undispatched terminal rows preserve the complete scoring denominator.
        for observation in plan:
            if observation["observation_id"] not in terminal_ids | started_ids:
                skip(observation, (halt or {"code": "incomplete"})["code"])
        cleanup = await asyncio.gather(*(close_client(name, engine) for name, engine in engines.items()))
        manifest["cleanup_errors"] = [error for error in cleanup if error]
        if manifest["cleanup_errors"]:
            stop("cleanup_failure", "Client cleanup failed after dispatch stopped.")
        manifest["finished_at"] = _utc_now()
        manifest["elapsed_seconds"] = time.perf_counter() - whole_start
        manifest["paid_elapsed_seconds"] = dispatch_end - paid_start if paid_start else 0
        manifest["measured_elapsed_seconds"] = dispatch_end - measured_start if measured_start else 0
        manifest["missing_terminal_count"] = len(started_ids - terminal_ids)
        manifest["budget"] = budget.public()
        _atomic_json(manifest_path, manifest)
    return write_report(output)


async def run(config: dict, datasets: dict[str, list[dict]], output: Path,
              *, prepared_path: Path | None = None) -> dict:
    validate_config(config)
    if config.get("experiment_kind") != REAL_PROFILE:
        if prepared_path is not None:
            raise ValueError("Prepared receipts are only supported by the bounded real-document profile")
        return await _run_legacy(config, datasets, output)
    from .prepare import load_prepared, validate_profile

    validate_profile(config, datasets, root=ROOT)
    if prepared_path is None:
        raise ValueError("The real-document study requires --prepared after local --prepare-only")
    receipt, documents = load_prepared(config, datasets, Path(prepared_path), root=ROOT)
    return await _run_prepared(config, datasets, output, Path(prepared_path), receipt, documents)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "benchmarks/configs/default.yaml")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--prepare-only", action="store_true", help="Prepare the bounded study locally; no inference clients or calls")
    mode.add_argument("--prepared", type=Path, help="Execute once using a verified local preparation receipt")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int, help="Explicit small pilot: maximum test items per task")
    parser.add_argument("--repeats", type=int)
    parser.add_argument("--concurrency", type=int, choices=[1, 4])
    parser.add_argument("--scope", choices=["decision", "end-to-end"])
    arguments = parser.parse_args()
    config = load_config(arguments.config)
    for name in ("repeats", "concurrency", "scope"):
        value = getattr(arguments, name)
        if value is not None:
            config[name] = value
    if config["repeats"] < 1:
        parser.error("--repeats must be positive")
    if arguments.limit is not None and arguments.limit < 1:
        parser.error("--limit must be positive")
    config["pilot_limit_per_task"] = arguments.limit
    validate_config(config)
    if config.get("experiment_kind") == REAL_PROFILE:
        from .prepare import validate_profile

        validate_profile(config, root=ROOT)
        if not (arguments.dry_run or arguments.prepare_only or arguments.prepared):
            parser.error("The real-document study requires --prepared after local --prepare-only")
    datasets = load_datasets(config, limit=arguments.limit)
    if config.get("experiment_kind") == REAL_PROFILE:
        validate_profile(config, datasets, root=ROOT)
    if arguments.dry_run:
        print(json.dumps(dry_run(config, datasets), indent=2))
        return
    output = arguments.output or ROOT / "benchmarks/results" / datetime.now(UTC).strftime("run-%Y%m%dT%H%M%SZ")
    if arguments.prepare_only:
        if config.get("experiment_kind") != REAL_PROFILE:
            parser.error("--prepare-only requires the bounded real-document profile")
        from .prepare import prepare_corpus

        receipt = prepare_corpus(config, datasets, output.resolve(), root=ROOT)
        print(json.dumps(receipt, indent=2))
        if receipt.get("status") != "ready":
            raise SystemExit(1)
        return
    summary = asyncio.run(run(config, datasets, output.resolve(), prepared_path=arguments.prepared))
    print(json.dumps({"output": str(output), "groups": len(summary["groups"]), "status": summary["run_status"]}))
    if summary["run_status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

"""Run frozen-data, budgeted comparisons. No API calls occur in --dry-run."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import math
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
from jev_docs.errors import JevDocsError
from jev_docs.rules import load_rules
from jev_docs.schemas import ParsedDocument, RunMetrics
from jev_docs.split import asplit_document

from .report import write_report

ROOT = Path(__file__).resolve().parents[1]


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

    async def settle(self, reserved: float, requests: list[dict], *, dispatched: bool) -> None:
        known = sum(record["cost_usd"] for record in requests if record.get("cost_usd") is not None)
        unknown = dispatched and (not requests or any(record.get("cost_usd") is None for record in requests))
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
    return config


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


def reservation(engine: str, item: dict, document: ParsedDocument | None,
                config: dict, rules_text: str) -> float:
    pages = item["page_count"]
    if engine == "jev":
        windows = max(1, math.ceil(pages / config.get("window_size", 8)))
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
    return {"dry_run": True, "remote_calls": 0, "tasks": tasks, "budget_usd": config["budget_usd"],
            "estimated_upper_reservations_usd": reserved, "within_estimated_budget": reserved <= config["budget_usd"],
            "note": "Preflight estimate assumes 12,000 OCR bytes/page; real dispatch reservations use actual text bytes. It is not a provider billing cap."}


async def run(config: dict, datasets: dict[str, list[dict]], output: Path) -> dict:
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory is not empty; choose a new run directory")
    output.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC).isoformat()
    source_files = [*list((ROOT / "src/jev_docs/engines").glob("*.py")),
                    ROOT / "src/jev_docs/windows.py", ROOT / "src/jev_docs/split.py",
                    ROOT / "src/jev_docs/classify.py", ROOT / "benchmarks/pricing.json"]
    packages = {}
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
    engines = {"jev": JevEngine(model=config["jev_model"], max_retries=0, window_size=config.get("window_size", 8)),
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "benchmarks/configs/default.yaml")
    parser.add_argument("--dry-run", action="store_true")
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
    datasets = load_datasets(config, limit=arguments.limit)
    if arguments.dry_run:
        print(json.dumps(dry_run(config, datasets), indent=2))
        return
    output = arguments.output or ROOT / "benchmarks/results" / datetime.now(UTC).strftime("run-%Y%m%dT%H%M%SZ")
    summary = asyncio.run(run(config, datasets, output.resolve()))
    print(json.dumps({"output": str(output), "groups": len(summary["groups"]), "status": summary["run_status"]}))


if __name__ == "__main__":
    main()

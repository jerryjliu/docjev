"""Local, bounded OCR preparation and sealed input receipts for the real pilot."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import re
import runpy
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jev_docs.cache import atomic_write, cache_key, digest_file
from jev_docs.engines.jev import JevEngine
from jev_docs.engines.openai import OpenAIEngine
from jev_docs.ocr.liteparse import parser_info
from jev_docs.rules import load_rules
from jev_docs.schemas import ParsedDocument, RunMetrics

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "real-document-accuracy-pilot"
CORPUS = "datasets/real-small/v1"
LABELS = {"tax_form", "financial_report", "press_release", "legal_notice", "other"}
LIMITS = {"ocr_timeout_s": 60, "preparation_timeout_s": 600, "request_timeout_s": 30,
          "task_timeout_s": 60, "paid_timeout_s": 300, "cleanup_timeout_s": 5}


def _verify_corpus(root: Path) -> dict:
    verifier = runpy.run_path(str(root / "datasets/real-small/prepare.py"))["verify_corpus"]
    return verifier(root, require_review=True, render=False)


def validate_profile(config: dict, datasets: dict | None = None, *, root: Path = ROOT) -> None:
    """Prevent command-line overrides from silently enlarging the fixed study."""
    if config.get("experiment_kind") != PROFILE:
        return
    required = {"repeats": 1, "warmups": 1, "concurrency": 1, "scope": "decision",
                "ocr": "liteparse", "jev_model": "jev-1.13.0", "baseline_model": "gpt-5.6-luna",
                "max_retries": 0, "context_recovery": False, "window_size": 8}
    for field, expected in required.items():
        if config.get(field) != expected:
            raise ValueError(f"The real-small profile requires {field}={expected!r}")
    if config.get("pilot_limit_per_task") is not None:
        raise ValueError("The frozen real-small profile cannot use --limit")
    if config.get("warmup_policy", "dev") not in {"dev", "development"}:
        raise ValueError("The real-small profile requires separate development warmups")
    for field, ceiling in {"budget_usd": 2, **LIMITS}.items():
        value = config.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= ceiling:
            raise ValueError(f"The real-small profile requires 0 < {field} <= {ceiling}")
    if set(config.get("tasks", {})) != {"classify", "split"}:
        raise ValueError("The real-small profile requires both tasks")
    for task, paths in config["tasks"].items():
        if paths.get("manifest") != f"{CORPUS}/manifests/{task}.json" or paths.get("rules") != f"{CORPUS}/rules/{task}.yaml":
            raise ValueError("The real-small profile must use the frozen v1 corpus and rules")
    if datasets is None:
        return
    if set(datasets) != {"classify", "split"}:
        raise ValueError("Both frozen datasets are required")
    ids = [item["id"] for items in datasets.values() for item in items]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r"[A-Za-z0-9_-]+", value) for value in ids):
        raise ValueError("Input IDs must be globally unique safe filenames")
    for task, items in datasets.items():
        if any(item.get("split") not in {"dev", "test"} for item in items):
            raise ValueError("Unknown dataset partition")
        if sum(item["split"] == "dev" for item in items) != 1:
            raise ValueError("Exactly one separate development input is required per task")
        frozen = json.loads((root / config["tasks"][task]["manifest"]).read_text())
        # The loader partitions development first while preserving order within each split.
        expected_items = [row for partition in ("dev", "test") for row in frozen if row["split"] == partition]
        if items != expected_items or len(items) != len(frozen):
            raise ValueError("Loaded dataset differs from the complete frozen manifest")
    originals = [item for item in datasets["classify"] if item["split"] == "test"]
    packets = [item for item in datasets["split"] if item["split"] == "test"]
    if len(originals) != 40 or Counter(item["category"] for item in originals) != Counter(dict.fromkeys(LABELS, 8)):
        raise ValueError("The corpus requires five categories with eight originals each")
    if sum(item["page_count"] for item in originals) > 160 or len(packets) != 8:
        raise ValueError("The corpus exceeds the original-page or packet-count contract")
    if any(item["page_count"] > 25 or len(item["source_ids"]) != 5 for item in packets):
        raise ValueError("Packets require five complete originals and at most 25 pages")
    if Counter(source for item in packets for source in item["source_ids"]) != Counter(item["id"] for item in originals):
        raise ValueError("Each original must appear in exactly one packet")
    _verify_corpus(root)


def _identity(config: dict, datasets: dict, root: Path) -> dict:
    code = sorted({*ROOT.glob("benchmarks/*.py"), *ROOT.glob("src/jev_docs/**/*.py"),
                   ROOT / "benchmarks/pricing.json", ROOT / "pyproject.toml",
                   ROOT / "uv.lock", ROOT / "datasets/real-small/prepare.py"})
    packages: dict[str, str | None] = {}
    for name in ("docjev", "liteparse", "typesafe-sdk", "openai", "pydantic", "pypdf", "pypdfium2", "Pillow"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "config_sha256": cache_key(config), "datasets_sha256": cache_key(datasets),
        "corpus_freeze_sha256": digest_file(root / CORPUS / "FREEZE.json"),
        "source_hashes": {str(path.relative_to(ROOT)): digest_file(path) for path in code if path.is_file()},
        "input_manifest_hashes": {task: digest_file(root / setting["manifest"]) for task, setting in config["tasks"].items()},
        "rules_hashes": {task: digest_file(root / setting["rules"]) for task, setting in config["tasks"].items()},
        "input_hashes": {item["id"]: digest_file(root / item["path"]) for items in datasets.values() for item in items},
        "packages": packages, "parser": parser_info().model_dump(),
    }


def _seal(receipt: dict) -> str:
    return cache_key({key: value for key, value in receipt.items() if key != "receipt_sha256"})


def _save_receipt(path: Path, receipt: dict) -> None:
    receipt["receipt_sha256"] = _seal(receipt)
    atomic_write(path, (json.dumps(receipt, indent=2) + "\n").encode())


def _bounded_process(command: list[str], *, timeout: float, cwd: Path, env: dict | None = None) -> int:
    """Kill and reap the process group, including any native OCR descendants."""
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        return process.wait(timeout=timeout)
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=2)


def _parse_in_subprocess(item: dict, config: dict, root: Path, timeout: float) -> ParsedDocument:
    scratch_root = root / ".jev-docs/benchmark-workers"
    scratch_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch_root) as directory:
        request_path = Path(directory) / "request.json"
        response_path = Path(directory) / "response.json"
        request_path.write_text(json.dumps({"source": str(root / item["path"]),
                                           "cache_dir": str(root / ".jev-docs/cache"),
                                           "response_path": str(response_path)}))
        environment = {key: value for key, value in os.environ.items() if key not in {
            "TYPESAFE_API_KEY", "JEV_API_KEY", "OPENAI_API_KEY", "LLAMA_CLOUD_API_KEY"}}
        code = _bounded_process([sys.executable, "-m", "benchmarks.prepare", "--worker", str(request_path)],
                                timeout=timeout, cwd=ROOT, env=environment)
        if code or not response_path.is_file():
            raise ValueError("Local OCR worker did not produce an artifact")
        response = json.loads(response_path.read_text())
        if response["status"] != "ok":
            raise ValueError(f"Local OCR worker failed ({response['error_type']})")
        return ParsedDocument.model_validate(response["document"])


def _worker(path: Path) -> None:
    from jev_docs.documents import parse_document

    request = json.loads(path.read_text())
    try:
        document = parse_document(request["source"], ocr="liteparse", cache_dir=request["cache_dir"])
        response = {"status": "ok", "document": document.model_dump()}
    except Exception as exc:
        response = {"status": "error", "error_type": type(exc).__name__}
    atomic_write(Path(request["response_path"]), json.dumps(response).encode())


def prepare_corpus(config: dict, datasets: dict, output: Path, *, root: Path = ROOT) -> dict:
    """Read all frozen inputs locally; never construct an inference client."""
    from .run import build_execution_plan, reservation

    started = time.monotonic()
    validate_profile(config, datasets, root=root)
    if config.get("experiment_kind") != PROFILE:
        raise ValueError("Separate preparation currently supports the real-small profile only")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Preparation directory is not empty; choose a new directory")
    output.mkdir(parents=True, exist_ok=True)
    preparation_id = uuid.uuid4().hex
    artifact_root = root / ".jev-docs/benchmark-parsed" / preparation_id
    artifact_root.mkdir(parents=True)
    receipt: dict[str, Any] = {
        "schema_version": "1", "preparation_id": preparation_id, "status": "preparing",
        "started_at": datetime.now(UTC).isoformat(), "config": config,
        "identity": _identity(config, datasets, root), "execution_plan": build_execution_plan(config, datasets),
        "items": {}, "blockers": [], "remote_calls": 0,
        "note": "LiteParse preparation only; no decision provider was called. Cache hits are not cold OCR measurements.",
    }
    receipt_path = output / "preparation.json"
    rules = {task: load_rules(root / setting["rules"]) for task, setting in config["tasks"].items()}
    documents = {}
    _save_receipt(receipt_path, receipt)
    for task, items in datasets.items():
        for item in items:
            entry = {"status": "error", "task": task, "partition": item["split"],
                     "source_sha256": item["sha256"], "page_count": item["page_count"],
                     "source_ids": item.get("source_ids", []),
                     "source_family_id": item.get("source_family_id"),
                     "preparation_metrics": RunMetrics(ocr_cost_usd=0, ocr_cost_status="not_applicable").model_dump(),
                     "cache_hit": False, "engine_preflight": {}}
            start = time.monotonic()
            remaining = config["preparation_timeout_s"] - (start - started)
            try:
                if remaining <= 0:
                    raise TimeoutError("Total preparation deadline exceeded")
                document = _parse_in_subprocess(item, config, root, min(config["ocr_timeout_s"], remaining))
                # Retain telemetry even if a later identity/coverage check fails.
                entry["preparation_metrics"] = document.metrics.model_dump()
                entry["cache_hit"] = document.metrics.ocr_cache_hit
                if document.source_sha256 != item["sha256"] or document.page_count != item["page_count"]:
                    raise ValueError("Parsed identity or page count differs from frozen source")
                if document.parser.name != "liteparse" or document.metrics.requests:
                    raise ValueError("Only local LiteParse is allowed in this preparation")
                artifact_path = artifact_root / f"{item['id']}.json"
                atomic_write(artifact_path, document.model_dump_json(indent=2).encode())
                entry.update(status="ok", artifact=str(artifact_path.relative_to(root)),
                             artifact_sha256=digest_file(artifact_path),
                             pages_sha256=cache_key({"pages": [page.model_dump() for page in document.pages]}),
                             canonical_sha256=document.canonical_sha256,
                             parser=document.parser.model_dump(),
                             text_bytes=sum(len(page.text.encode()) for page in document.pages))
                documents[item["id"]] = document
                for name, engine in (("jev", JevEngine), ("openai", OpenAIEngine)):
                    try:
                        kwargs = {"window_size": config["window_size"]} if name == "jev" else {}
                        detail = engine.preflight(document, rules[task], task, **kwargs)
                        entry["engine_preflight"][name] = {"status": "ok", **detail}
                    except Exception as exc:
                        entry["engine_preflight"][name] = {"status": "error", "error": {
                            "type": type(exc).__name__, "message": "Prepared input exceeds the supported local decision contract; no request dispatched."}}
            except (TimeoutError, subprocess.TimeoutExpired) as exc:
                entry["error"] = {"type": type(exc).__name__, "message": "Local preparation deadline exceeded"}
                if time.monotonic() - started >= config["preparation_timeout_s"]:
                    if "preparation_deadline" not in receipt["blockers"]:
                        receipt["blockers"].append("preparation_deadline")
            except Exception as exc:
                entry["error"] = {"type": type(exc).__name__, "message": "Local OCR or source verification failed; this input remains in the denominator."}
            entry["wall_ms"] = (time.monotonic() - start) * 1000
            receipt["items"][item["id"]] = entry
            if item["split"] == "dev" and (entry["status"] != "ok" or any(value["status"] != "ok" for value in entry["engine_preflight"].values())):
                receipt["blockers"].append(f"warmup_preparation_failed:{item['id']}")
            _save_receipt(receipt_path, receipt)
            print(f"prepare {task} {item['id']}: {entry['status']} ({entry['wall_ms']:.0f} ms)", file=sys.stderr, flush=True)
    estimate = 0.0
    dispatchable = 0
    item_index = {item["id"]: item for items in datasets.values() for item in items}
    for observation in receipt["execution_plan"]:
        source_id, name, task = observation["source_id"], observation["engine"], observation["task"]
        entry = receipt["items"][source_id]
        if entry["status"] == "ok" and entry["engine_preflight"][name]["status"] == "ok":
            amount = reservation(name, item_index[source_id], documents[source_id], config, rules[task].model_dump_json())
            observation["reserved_cost_usd"] = amount
            estimate += amount
            dispatchable += 1
    receipt["budget_estimate"] = {"estimated_upper_reservations_usd": estimate,
                                  "budget_usd": config["budget_usd"],
                                  "within_estimated_budget": estimate <= config["budget_usd"],
                                  "planned_task_calls": len(receipt["execution_plan"]),
                                  "dispatchable_task_calls": dispatchable,
                                  "is_provider_billing_cap": False}
    if estimate > config["budget_usd"]:
        receipt["blockers"].append("estimated_budget_exceeded")
    if _identity(config, datasets, root) != receipt["identity"]:
        receipt["blockers"].append("identity_changed_during_preparation")
    receipt["elapsed_seconds"] = time.monotonic() - started
    if receipt["elapsed_seconds"] >= config["preparation_timeout_s"] and "preparation_deadline" not in receipt["blockers"]:
        receipt["blockers"].append("preparation_deadline")
    receipt["finished_at"] = datetime.now(UTC).isoformat()
    receipt["status"] = "blocked" if receipt["blockers"] else "ready"
    _save_receipt(receipt_path, receipt)
    return receipt


def load_prepared(config: dict, datasets: dict, receipt_path: Path, *, root: Path = ROOT) -> tuple[dict, dict[str, ParsedDocument]]:
    """Revalidate receipt and local artifacts; do not reparse or construct clients."""
    from .run import build_execution_plan, reservation

    validate_profile(config, datasets, root=root)
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("receipt_sha256") != _seal(receipt):
        raise ValueError("Preparation receipt checksum changed")
    if receipt.get("identity") != _identity(config, datasets, root):
        raise ValueError("Preparation identity changed; no provider was called")
    if receipt.get("status") not in {"ready", "blocked"}:
        raise ValueError("Preparation did not finish")
    expected = build_execution_plan(config, datasets)
    actual = [{key: value for key, value in row.items() if key != "reserved_cost_usd"}
              for row in receipt["execution_plan"]]
    if actual != expected:
        raise ValueError("Preparation execution plan changed")
    items = {item["id"]: item for group in datasets.values() for item in group}
    if set(receipt["items"]) != set(items):
        raise ValueError("Preparation omitted frozen inputs")
    documents = {}
    artifact_root = (root / ".jev-docs/benchmark-parsed").resolve()
    for source_id, entry in receipt["items"].items():
        if entry["status"] != "ok":
            continue
        path = (root / entry["artifact"]).resolve()
        if not path.is_relative_to(artifact_root) or digest_file(path) != entry["artifact_sha256"]:
            raise ValueError("Prepared artifact identity changed")
        document = ParsedDocument.model_validate_json(path.read_text())
        canonical = Path(document.canonical_path).resolve()
        if not canonical.is_relative_to((root / ".jev-docs").resolve()) or digest_file(canonical) != entry["canonical_sha256"]:
            raise ValueError("Prepared canonical PDF changed")
        if document.source_sha256 != items[source_id]["sha256"] or document.page_count != items[source_id]["page_count"]:
            raise ValueError("Prepared source identity changed")
        if cache_key({"pages": [page.model_dump() for page in document.pages]}) != entry["pages_sha256"]:
            raise ValueError("Prepared page text changed")
        document.metrics = RunMetrics(ocr_cache_hit=True, ocr_cost_usd=0, ocr_cost_status="not_applicable")
        documents[source_id] = document
    rules = {task: load_rules(root / setting["rules"]) for task, setting in config["tasks"].items()}
    amount = 0.0
    count = 0
    for observation in receipt["execution_plan"]:
        source_id, engine, task = observation["source_id"], observation["engine"], observation["task"]
        entry = receipt["items"][source_id]
        if entry["status"] == "ok" and entry["engine_preflight"][engine]["status"] == "ok":
            reserved = reservation(engine, items[source_id], documents[source_id], config, rules[task].model_dump_json())
            if not math.isclose(reserved, observation.get("reserved_cost_usd", -1), rel_tol=1e-12):
                raise ValueError("Prepared reservation changed")
            amount += reserved
            count += 1
    estimate = receipt["budget_estimate"]
    if count != estimate["dispatchable_task_calls"] or not math.isclose(amount, estimate["estimated_upper_reservations_usd"], rel_tol=1e-12):
        raise ValueError("Prepared total reservation changed")
    if receipt["status"] == "ready" and (amount > config["budget_usd"] or receipt["blockers"]):
        raise ValueError("Preparation does not pass admission")
    return receipt, documents


def claim_prepared(receipt_path: Path, receipt: dict, output: Path, *, root: Path = ROOT) -> None:
    """One local paid attempt per receipt, including attempts interrupted mid-call."""
    current = json.loads(receipt_path.read_text())
    if current.get("status") != "ready" or current.get("receipt_sha256") != _seal(current):
        raise ValueError("Only an intact ready preparation receipt can be claimed")
    if current["receipt_sha256"] != receipt["receipt_sha256"]:
        raise ValueError("Preparation receipt changed before claim")
    claims = root / ".jev-docs/benchmark-claims"
    claims.mkdir(parents=True, exist_ok=True)
    path = claims / f"{receipt['preparation_id']}.json"
    try:
        with path.open("x") as stream:
            json.dump({"receipt_sha256": receipt["receipt_sha256"], "run_id": output.name,
                       "claimed_at": datetime.now(UTC).isoformat()}, stream)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        raise ValueError("This preparation receipt already has an execution attempt; automatic replay is disabled") from None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path, required=True)
    _worker(parser.parse_args().worker)

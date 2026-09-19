"""Failure-inclusive task quality and document-level latency statistics."""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from statistics import mean
from typing import Any

REAL_ACCURACY_PILOT = "real-document-accuracy-pilot"
GROUP_FIELDS = ("task", "engine", "model", "scope", "concurrency")


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def prf(tp: int, predicted: int, actual: int) -> dict[str, float | int]:
    precision = tp / predicted if predicted else (1.0 if not actual else 0.0)
    recall = tp / actual if actual else 1.0
    return {"precision": precision, "recall": recall,
            "f1": 2 * tp / (predicted + actual) if predicted + actual else 1.0,
            "true_positive": tp, "predicted": predicted, "actual": actual}


def label_metrics(truth: list[str], prediction: list[str | None], labels: list[str]) -> dict[str, Any]:
    if len(truth) != len(prediction):
        raise ValueError("Truth and prediction must cover the same observations")
    confusion = {label: dict.fromkeys([*labels, "__missing__"], 0) for label in labels}
    for actual, guessed in zip(truth, prediction, strict=True):
        confusion[actual][guessed if guessed in labels else "__missing__"] += 1
    per_class = {}
    for label in labels:
        tp = sum(actual == guessed == label for actual, guessed in zip(truth, prediction, strict=True))
        per_class[label] = {**prf(tp, prediction.count(label), truth.count(label)), "support": truth.count(label)}
    correct = sum(a == p for a, p in zip(truth, prediction, strict=True))
    return {"correct_count": correct, "total_count": len(truth),
            "accuracy": correct / len(truth) if truth else None,
            "macro_f1": mean(float(value["f1"]) for value in per_class.values()) if per_class else None,
            "per_class": per_class, "confusion_matrix": confusion}


def _segments_key(segments: list[dict]) -> set[tuple[str, tuple[int, ...]]]:
    return {(segment["category"], tuple(segment["pages"])) for segment in segments}


def valid_segments(segments: Any, page_count: int) -> bool:
    if not isinstance(segments, list) or not segments:
        return False
    if any(not isinstance(segment, dict) or not isinstance(segment.get("category"), str)
           or not isinstance(segment.get("pages"), list) or not segment["pages"]
           or any(type(page) is not int for page in segment["pages"]) for segment in segments):
        return False
    return [page for segment in segments for page in segment["pages"]] == list(range(1, page_count + 1))


def packet_exact(actual: list[dict], predicted: Any, page_count: int) -> bool:
    """The same coverage check governs point estimates, intervals, and error IDs."""
    return valid_segments(predicted, page_count) and _segments_key(actual) == _segments_key(predicted)


def split_metrics(truth: list[list[dict]], predictions: list[list[dict] | None],
                  page_counts: list[int]) -> dict[str, Any]:
    if not len(truth) == len(predictions) == len(page_counts):
        raise ValueError("Each packet must have truth, prediction, and page count")
    boundary_counts = [0, 0, 0]
    segment_counts = [0, 0, 0]
    same_category_actual = same_category_found = exact = coverage_valid = 0
    all_truth: list[str] = []
    all_predictions: list[str | None] = []
    for actual, predicted, count in zip(truth, predictions, page_counts, strict=True):
        valid = valid_segments(predicted, count)
        coverage_valid += valid
        exact += packet_exact(actual, predicted, count)
        predicted = predicted if valid else None
        actual_boundaries = {segment["pages"][0] for segment in actual[1:]}
        predicted_boundaries = {segment["pages"][0] for segment in (predicted or [])[1:]}
        boundary_counts[0] += len(actual_boundaries & predicted_boundaries)
        boundary_counts[1] += len(predicted_boundaries)
        boundary_counts[2] += len(actual_boundaries)
        actual_segments = _segments_key(actual)
        predicted_segments = _segments_key(predicted or [])
        segment_counts[0] += len(actual_segments & predicted_segments)
        segment_counts[1] += len(predicted_segments)
        segment_counts[2] += len(actual_segments)
        same = {right["pages"][0] for left, right in zip(actual, actual[1:], strict=False)
                if left["category"] == right["category"]}
        same_category_actual += len(same)
        same_category_found += len(same & predicted_boundaries)
        actual_labels = {page: segment["category"] for segment in actual for page in segment["pages"]}
        predicted_labels = {page: segment["category"] for segment in (predicted or []) for page in segment["pages"]}
        all_truth.extend(actual_labels[page] for page in range(1, count + 1))
        all_predictions.extend(predicted_labels.get(page) for page in range(1, count + 1))
    labels = label_metrics(all_truth, all_predictions, sorted(set(all_truth)))
    return {"packet_exact_match": exact / len(truth) if truth else None,
            "exact_packets": exact, "total_packets": len(truth), "coverage_valid_packets": coverage_valid,
            "coverage_validity": coverage_valid / len(truth) if truth else None,
            "page_correct_count": labels["correct_count"], "page_total_count": labels["total_count"],
            "page_accuracy": labels["accuracy"], "page_macro_f1": labels["macro_f1"],
            "page_per_class": labels["per_class"], "page_confusion_matrix": labels["confusion_matrix"],
            "boundary": prf(*boundary_counts), "segment": prf(*segment_counts),
            "same_category_boundary_recall": same_category_found / same_category_actual if same_category_actual else None,
            "same_category_boundaries_found": same_category_found,
            "same_category_boundaries_actual": same_category_actual}


def bootstrap_mean(values: list[float], *, seed: int = 712, samples: int = 2000) -> list[float | None] | None:
    if len(values) < 2:
        return None
    randomizer = random.Random(seed)
    estimates = [mean(randomizer.choices(values, k=len(values))) for _ in range(samples)]
    return [percentile(estimates, 0.025), percentile(estimates, 0.975)]


def _source(row: dict) -> str:
    identity = row.get("source_id", row.get("id"))
    if not isinstance(identity, str):
        raise ValueError("Observation source ID must be a string")
    return identity


def _group(row: dict) -> tuple:
    return tuple(row[field] for field in GROUP_FIELDS)


def _identity(row: dict) -> tuple:
    return (*_group(row), row["phase"], row["repeat"], _source(row))


def _timing(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def _call_accounting(rows: list[dict], unclosed: list[dict]) -> dict:
    requests = [request for row in rows for request in row.get("requests", []) if request.get("task") != "ocr"]
    unknown_ids = set()
    incomplete = bool(unclosed)
    for index, row in enumerate(rows):
        records = [record for record in row.get("requests", []) if record.get("task") != "ocr"]
        missing_usage = row.get("usage_unknown", False) or any(record.get("cost_usd") is None for record in records)
        missing_requests = row.get("dispatched", False) and row["status"] != "ok" and not records
        if missing_usage or missing_requests or row.get("request_count_complete") is False:
            unknown_ids.add(row.get("observation_id", ("row", index)))
        incomplete |= missing_requests or row.get("request_count_complete") is False
    unknown_ids.update(event.get("observation_id", ("start", index)) for index, event in enumerate(unclosed))
    return {"decision_cost_usd_known": sum(record["cost_usd"] for record in requests if record.get("cost_usd") is not None),
            "unknown_cost_calls": len(unknown_ids), "request_count": len(requests),
            "request_count_complete": not incomplete,
            "unclosed_dispatch_reservations_usd": sum(event.get("reserved_cost_usd", 0) for event in unclosed),
            **{name + "_known": sum(record.get(name) or 0 for record in requests)
               for name in ("input_tokens", "output_tokens", "cached_input_tokens", "cache_write_tokens")}}


def preparation_accounting(preparation: dict | None) -> dict:
    items = (preparation or {}).get("items", {})
    known = 0.0
    unknown = 0
    conversion_ms = ocr_ms = wall_ms = 0.0
    cache_hits = successful = 0
    wall_samples = 0
    for item in items.values():
        metrics = item.get("preparation_metrics", {})
        cache_hit = item.get("cache_hit", metrics.get("ocr_cache_hit", False))
        cache_hits += bool(cache_hit)
        successful += item.get("status", "ok") == "ok"
        records = [record for record in metrics.get("requests", []) if record.get("task") == "ocr"]
        if cache_hit:
            pass  # Historical cached usage is never a charge for this preparation.
        elif records:
            known += sum(record["cost_usd"] for record in records if record.get("cost_usd") is not None)
            unknown += any(record.get("cost_usd") is None for record in records)
        elif metrics.get("ocr_cost_usd") is not None:
            known += metrics["ocr_cost_usd"]
        elif item.get("parser", {}).get("name") != "liteparse":
            unknown += 1
        conversion_ms += metrics.get("conversion_ms", 0)
        ocr_ms += metrics.get("ocr_ms", 0)
        wall = item.get("wall_ms", metrics.get("total_ms"))
        if _timing(wall):
            wall_ms += wall
            wall_samples += 1
    return {"items": len(items), "successful_items": successful, "failed_or_skipped_items": len(items) - successful,
            "cache_hits": cache_hits, "conversion_ms_known": conversion_ms, "ocr_ms_known": ocr_ms,
            "wall_ms_known": wall_ms, "wall_samples": wall_samples,
            "cost_usd_known": known, "unknown_cost_items": unknown,
            "local_compute_cost": "not_estimated", "elapsed_seconds": (preparation or {}).get("elapsed_seconds")}


def summarize(observations: list[dict], datasets: dict[str, list[dict]], *,
              execution_plan: list[dict] | None = None, events: list[dict] | None = None,
              preparation: dict | None = None, experiment_kind: str | None = None) -> dict[str, Any]:
    """Score the frozen first pass even if no terminal rows exist for a group."""
    plans = {row["observation_id"]: row for row in (execution_plan or [])}
    if len(plans) != len(execution_plan or []):
        raise ValueError("Duplicate planned observation ID")
    if len({_identity(row) for row in plans.values()}) != len(plans):
        raise ValueError("Duplicate planned observation identity")
    indexed = {task: {item["id"]: item for item in items} for task, items in datasets.items()}
    if any(len(indexed[task]) != len(items) for task, items in datasets.items()):
        raise ValueError("Duplicate dataset source ID")
    seen = set()
    terminal_ids = set()
    for row in observations:
        key = _identity(row)
        if key in seen:
            raise ValueError("Duplicate terminal observation")
        seen.add(key)
        if row["status"] not in ("ok", "error", "skipped"):
            raise ValueError("Unknown terminal status")
        if _source(row) not in indexed.get(row["task"], {}):
            raise ValueError("Unexpected observation source ID")
        if execution_plan is not None:
            planned = plans.get(row.get("observation_id"))
            if planned is None or _identity(planned) != key:
                raise ValueError("Observation does not match frozen execution plan")
            terminal_ids.add(row["observation_id"])
    starts = {}
    for event in events or []:
        if event.get("event", event.get("type")) != "dispatch_started":
            continue
        identity = event.get("observation_id")
        if execution_plan is not None and identity not in plans:
            raise ValueError("Unexpected dispatch observation ID")
        if identity in starts:
            raise ValueError("Duplicate dispatch start")
        starts[identity] = event
    terminals = {row.get("observation_id"): row for row in observations}
    # A start followed by a non-dispatched placeholder cannot erase a possible charge.
    unclosed = {identity: event for identity, event in starts.items()
                if identity not in terminal_ids or not terminals[identity].get("dispatched", False)
                or terminals[identity]["status"] == "skipped"}
    groups: dict[tuple, list[dict]] = defaultdict(list)
    planned_groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in plans.values():
        if row["phase"] == "measured":
            planned_groups[_group(row)].append(row)
            groups[_group(row)]
    for row in observations:
        if row["phase"] == "measured":
            groups[_group(row)].append(row)
    summaries = []
    for key, rows in sorted(groups.items()):
        task, engine, model, scope, concurrency = key
        expected = [item for item in datasets[task] if item["split"] == "test"]
        expected_ids = {item["id"] for item in expected}
        if any(_source(row) not in expected_ids for row in rows):
            raise ValueError("Measured observation must belong to the frozen test split")
        scheduled = planned_groups[key]
        if execution_plan is not None:
            first_planned = {_source(row) for row in scheduled if row["repeat"] == 0}
            if first_planned != expected_ids:
                raise ValueError("Execution plan does not cover the frozen first-pass denominator")
        first = {_source(row): row for row in rows if row["repeat"] == 0}
        def valid_result(row: dict, task: str = task) -> bool:
            if row.get("status") != "ok":
                return False
            result = row.get("result", {})
            if task == "classify":
                return isinstance(result.get("category"), str)
            return valid_segments(result.get("segments"), indexed[task][_source(row)]["page_count"])
        success_rows = [row for row in rows if valid_result(row)]
        completed = [row for row in first.values() if valid_result(row)]
        invalid = [row for row in rows if row["status"] == "ok" and not valid_result(row)]
        latencies = [row.get("result", {}).get("metrics", {}).get("decision_ms") for row in success_rows]
        decision_latencies = [value for value in latencies if _timing(value)]
        wall_latencies = [row["wall_ms"] for row in success_rows if _timing(row.get("wall_ms"))]
        missing_starts = [event for identity, event in unclosed.items() if identity in plans and _group(plans[identity]) == key and plans[identity]["phase"] == "measured"]
        repeats = max((row["repeat"] for row in scheduled or rows), default=0) + 1
        planned_calls = len(scheduled) if execution_plan is not None else len(expected) * repeats
        failed = [row for row in rows if row["status"] == "error"]
        skipped = [row for row in rows if row["status"] == "skipped"]
        errors = Counter(row.get("error", {}).get("type", "Unknown") for row in failed)
        errors.update({"InvalidResult": len(invalid)} if invalid else {})
        payload = {"task": task, "engine": engine, "model": model, "scope": scope,
                   "concurrency": concurrency, "planned_unique": len(expected),
                   "completed_unique": len(completed), "completion_rate": len(completed) / len(expected) if expected else None,
                   "planned_calls": planned_calls, "measured_calls": len(rows),
                   "dispatched_calls": sum(bool(row.get("dispatched", row["status"] == "ok")) for row in rows) + len(missing_starts),
                   "successful_calls": len(success_rows), "failed_calls": len(failed) + len(invalid),
                   "skipped_calls": len(skipped), "missing_terminal_calls": planned_calls - len(rows),
                   "unclosed_dispatches": len(missing_starts), "first_pass_missing": len(expected_ids - first.keys()),
                   "skip_reasons": dict(Counter(str(row.get("skip_reason", "unspecified")) for row in skipped)),
                   "error_types": dict(errors), "latency_samples": len(decision_latencies),
                   "wall_latency_samples": len(wall_latencies),
                   "decision_p50_ms": percentile(decision_latencies, .5), "decision_p95_ms": percentile(decision_latencies, .95),
                   "wall_p50_ms": percentile(wall_latencies, .5), "wall_p95_ms": percentile(wall_latencies, .95),
                   **_call_accounting(rows, missing_starts),
                   "ocr_cost_usd_known": sum(request["cost_usd"] for row in rows for request in row.get("requests", [])
                                             if request.get("task") == "ocr" and request.get("cost_usd") is not None)}
        results = [first.get(item["id"], {}) for item in expected]
        if task == "classify":
            actual = [item["category"] for item in expected]
            guesses = [row.get("result", {}).get("category") if valid_result(row) else None for row in results]
            payload.update(label_metrics(actual, guesses, sorted(set(actual))))
            correct = [float(a == p) for a, p in zip(actual, guesses, strict=True)]
            payload["accuracy_95pct_bootstrap"] = None if experiment_kind == REAL_ACCURACY_PILOT else bootstrap_mean(correct)
            payload["needs_review_rate"] = sum(row["result"].get("needs_review", False) for row in completed) / len(expected) if expected else None
        else:
            actual = [item["segments"] for item in expected]
            guesses = [row.get("result", {}).get("segments") if valid_result(row) else None for row in results]
            counts = [item["page_count"] for item in expected]
            payload.update(split_metrics(actual, guesses, counts))
            correct = [float(packet_exact(a, p, count)) for a, p, count in zip(actual, guesses, counts, strict=True)]
            payload["packet_exact_match_95pct_bootstrap"] = None if experiment_kind == REAL_ACCURACY_PILOT else bootstrap_mean(correct)
        disagreements = 0
        for item in expected:
            item_rows = [row for row in success_rows if _source(row) == item["id"]]
            values = ({row["result"]["category"] for row in item_rows} if task == "classify" else
                      {tuple(sorted(_segments_key(row["result"]["segments"]))) for row in item_rows})
            disagreements += len(values) > 1
        payload["repeat_disagreement_documents"] = disagreements if repeats > 1 else None
        payload["repeat_disagreement_status"] = "measured" if repeats > 1 else "not_measured"
        payload["failures_or_incorrect_ids"] = [item["id"] for item, matched in zip(expected, correct, strict=True) if not matched]
        summaries.append(payload)
    components = {"preparation": preparation_accounting(preparation)}
    for phase in ("warmup", "measured"):
        rows = [row for row in observations if row["phase"] == phase]
        unmatched = [event for identity, event in unclosed.items() if identity in plans and plans[identity]["phase"] == phase]
        components[phase] = {"planned_calls": sum(row["phase"] == phase for row in plans.values()) if execution_plan is not None else None,
                             "recorded_calls": len(rows), "dispatched_calls": sum(bool(row.get("dispatched", row["status"] == "ok")) for row in rows) + len(unmatched),
                             "successful_calls": sum(row["status"] == "ok" for row in rows),
                             "wall_ms_known": sum(row["wall_ms"] for row in rows if _timing(row.get("wall_ms"))),
                             **_call_accounting(rows, unmatched)}
    return {"schema_version": "1", "quality_pass": 0, "groups": summaries, "components": components,
            "unclosed_dispatches": len(unclosed), "missing_terminal_calls": len(plans) - len(terminal_ids) if execution_plan is not None else None,
            "cost_includes_warmups": False, "uncertainty_method": "omitted_curated_pilot" if experiment_kind == REAL_ACCURACY_PILOT else "source_bootstrap",
            "accuracy_unit": "unique source document or packet, first measured pass",
            "latency_unit": "successful complete document or packet, all measured passes"}

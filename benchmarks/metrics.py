"""Failure-inclusive task quality and document-level latency statistics."""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from statistics import mean
from typing import Any


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
        per_class[label] = prf(tp, prediction.count(label), truth.count(label))
    return {"accuracy": sum(a == p for a, p in zip(truth, prediction, strict=True)) / len(truth) if truth else None,
            "macro_f1": mean(float(value["f1"]) for value in per_class.values()) if per_class else None,
            "per_class": per_class, "confusion_matrix": confusion}


def _segments_key(segments: list[dict]) -> set[tuple[str, tuple[int, ...]]]:
    return {(segment["category"], tuple(segment["pages"])) for segment in segments}


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
        covered = [page for segment in (predicted or []) for page in segment["pages"]]
        valid = predicted is not None and covered == list(range(1, count + 1))
        coverage_valid += valid
        predicted = predicted if valid else None
        exact += predicted is not None and _segments_key(actual) == _segments_key(predicted)
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
            "exact_packets": exact, "coverage_validity": coverage_valid / len(truth) if truth else None,
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


def summarize(observations: list[dict], datasets: dict[str, list[dict]]) -> dict[str, Any]:
    measured = [row for row in observations if row.get("phase") == "measured"]
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in measured:
        groups[(row["task"], row["engine"], row["model"], row["scope"], row["concurrency"])].append(row)
    summaries = []
    for (task, engine, model, scope, concurrency), rows in sorted(groups.items()):
        first = {row["id"]: row for row in rows if row["repeat"] == 0}
        expected = [item for item in datasets[task] if item["split"] == "test"]
        # An interrupted/partial run never narrows the frozen quality denominator.
        for item in expected:
            first.setdefault(item["id"], {"status": "missing", "result": {}})
        completed = [row for row in first.values() if row["status"] == "ok"]
        success_rows = [row for row in rows if row["status"] == "ok"]
        decision_latencies = [row["result"]["metrics"]["decision_ms"] for row in success_rows]
        measured_latencies = [row["wall_ms"] for row in success_rows]
        all_requests = [request for row in rows for request in row.get("requests", [])]
        decision_requests = [request for request in all_requests if request.get("task") != "ocr"]
        costs = [request.get("cost_usd") for request in decision_requests]
        unknown = 0
        for row in rows:
            requests = [request for request in row.get("requests", []) if request.get("task") != "ocr"]
            if any(request.get("cost_usd") is None for request in requests) or (
                row.get("dispatched") and row["status"] != "ok" and not requests
            ):
                unknown += 1
        payload = {"task": task, "engine": engine, "model": model, "scope": scope,
                   "concurrency": concurrency, "planned_unique": len(first),
                   "completed_unique": len(completed), "completion_rate": len(completed) / len(first),
                   "measured_calls": len(rows), "latency_samples": len(success_rows),
                   "decision_p50_ms": percentile(decision_latencies, 0.5),
                   "decision_p95_ms": percentile(decision_latencies, 0.95),
                   "wall_p50_ms": percentile(measured_latencies, 0.5),
                   "wall_p95_ms": percentile(measured_latencies, 0.95),
                   "decision_cost_usd_known": sum(cost for cost in costs if cost is not None),
                   "unknown_cost_calls": unknown,
                   "failed_calls": len(rows) - len(success_rows),
                   "error_types": dict(Counter(row.get("error", {}).get("type", "Unknown")
                                              for row in rows if row["status"] != "ok")),
                   "request_count": len(decision_requests),
                   "input_tokens_known": sum(request.get("input_tokens") or 0 for request in decision_requests),
                   "cached_input_tokens_known": sum(request.get("cached_input_tokens") or 0 for request in decision_requests),
                   "cache_write_tokens_known": sum(request.get("cache_write_tokens") or 0 for request in decision_requests),
                   "output_tokens_known": sum(request.get("output_tokens") or 0 for request in decision_requests),
                   "ocr_cost_usd_known": sum(request["cost_usd"] for request in all_requests
                                             if request.get("task") == "ocr" and request.get("cost_usd") is not None)}
        if task == "classify":
            actual = [item["category"] for item in expected]
            guesses = [first[item["id"]].get("result", {}).get("category") for item in expected]
            payload.update(label_metrics(actual, guesses, sorted(set(actual))))
            correct = [float(a == p) for a, p in zip(actual, guesses, strict=True)]
            payload["accuracy_95pct_bootstrap"] = bootstrap_mean(correct)
            payload["needs_review_rate"] = sum(row["result"]["needs_review"] for row in completed) / len(first)
        else:
            actual = [item["segments"] for item in expected]
            guesses = [first[item["id"]].get("result", {}).get("segments") for item in expected]
            payload.update(split_metrics(actual, guesses, [item["page_count"] for item in expected]))
            correct = [float(p is not None and _segments_key(a) == _segments_key(p))
                       for a, p in zip(actual, guesses, strict=True)]
            payload["packet_exact_match_95pct_bootstrap"] = bootstrap_mean(correct)
        disagreements = 0
        for item in expected:
            item_rows = [row for row in rows if row["id"] == item["id"] and row["status"] == "ok"]
            if task == "classify":
                values = {row["result"]["category"] for row in item_rows}
            else:
                values = {tuple(sorted(_segments_key(row["result"]["segments"]))) for row in item_rows}
            disagreements += len(values) > 1
        payload["repeat_disagreement_documents"] = disagreements
        payload["failures_or_incorrect_ids"] = [item["id"] for item, is_correct in zip(expected, correct, strict=True) if not is_correct]
        summaries.append(payload)
    return {"schema_version": "1", "quality_pass": 0, "groups": summaries,
            "cost_includes_warmups": False,
            "accuracy_unit": "unique source document or packet, first measured pass",
            "latency_unit": "completed full document or packet, all measured passes"}

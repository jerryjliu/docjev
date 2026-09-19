"""Generate a shareable report from recorded observations, without provider calls."""

from __future__ import annotations

import argparse
import base64
import csv
import html
import json
from pathlib import Path

from .metrics import REAL_ACCURACY_PILOT, summarize


def number(value: float | None, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}" if value is not None else "n/a"


def _read_jsonl(path: Path) -> tuple[list[dict], bool]:
    """A hard kill can leave one unfinished final write; earlier corruption is an error."""
    if not path.is_file():
        return [], False
    lines = path.read_text().splitlines()
    rows = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if index == len(lines) - 1:
                return rows, True
            raise ValueError(f"Invalid interior JSONL record in {path.name}") from None
    return rows, False


def _preparation(manifest: dict, output: Path) -> dict:
    receipt_path = output / "preparation.json"
    if "preparation_receipt" in manifest or "preparation" in manifest or receipt_path.is_file():
        receipt = manifest.get("preparation_receipt", manifest.get("preparation"))
        if receipt is None:
            receipt = json.loads(receipt_path.read_text())
        return {**receipt, "items": {identity: {"parser": {"name": manifest["config"].get("ocr")}, **item}
                                    for identity, item in receipt.get("items", {}).items()}}
    return {"items": {identity: {"status": "ok", **item}
                      for identity, item in manifest.get("parsed_artifacts", {}).items()}}


def write_report(output: Path) -> dict:
    manifest = json.loads((output / "manifest.json").read_text())
    observations, truncated_raw = _read_jsonl(output / "raw.jsonl")
    events, truncated_events = _read_jsonl(output / "events.jsonl")
    config = manifest["config"]
    kind = manifest.get("experiment_kind", config.get("experiment_kind", "heldout-synthetic-benchmark"))
    summary = summarize(observations, manifest["datasets"], execution_plan=manifest.get("execution_plan"),
                        events=events, preparation=_preparation(manifest, output), experiment_kind=kind)
    recorded_status = manifest.get("status", "unknown")
    incomplete = bool(summary["missing_terminal_calls"] or summary["unclosed_dispatches"] or truncated_raw or truncated_events)
    status = "incomplete" if recorded_status in ("running", "unknown") or (recorded_status == "complete" and incomplete) else recorded_status
    summary.update(run_id=manifest["run_id"], config=config,
                   demo_set=manifest.get("demo_set", config.get("demo_set", "synthetic")), experiment_kind=kind,
                   started_at=manifest["started_at"], run_status=status, recorded_run_status=recorded_status,
                   stop_reason=manifest.get("stop_reason"), budget=manifest.get("budget", {}),
                   truncated_final_records={"raw": truncated_raw, "events": truncated_events},
                   configured_warmups_per_engine_task=config.get("warmups"),
                   pricing_snapshot=manifest.get("pricing_snapshot"))
    prep = summary["components"]["preparation"]
    warmup = summary["components"]["warmup"]
    measured = summary["components"]["measured"]
    embedded_ocr = [request for row in observations for request in row.get("requests", []) if request.get("task") == "ocr"]
    summary["components"]["task_ocr"] = {
        "cost_usd_known": sum(request["cost_usd"] for request in embedded_ocr if request.get("cost_usd") is not None),
        "unknown_cost_requests": sum(request.get("cost_usd") is None for request in embedded_ocr),
        "request_count": len(embedded_ocr)}
    known_total = prep["cost_usd_known"] + warmup["decision_cost_usd_known"] + measured["decision_cost_usd_known"] + summary["components"]["task_ocr"]["cost_usd_known"]
    unknown_total = prep["unknown_cost_items"] + warmup["unknown_cost_calls"] + measured["unknown_cost_calls"] + summary["components"]["task_ocr"]["unknown_cost_requests"]
    summary["accounting"] = {"full_run_cost_usd_known": known_total, "unknown_cost_observations": unknown_total,
                             "known_cost_is_lower_bound": bool(unknown_total),
                             "includes_warmups_and_preparation": True}
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    fields = ["task", "engine", "model", "scope", "concurrency", "planned_unique", "completed_unique",
              "correct_count", "exact_packets", "completion_rate", "accuracy", "macro_f1", "packet_exact_match", "page_accuracy",
              "page_macro_f1", "coverage_validity", "coverage_valid_packets", "same_category_boundary_recall",
              "same_category_boundaries_found", "same_category_boundaries_actual",
              "boundary_precision", "boundary_recall", "boundary_f1", "boundary_true_positive", "boundary_predicted", "boundary_actual",
              "segment_precision", "segment_recall", "segment_f1", "segment_true_positive", "segment_predicted", "segment_actual",
              "planned_calls", "dispatched_calls", "successful_calls", "failed_calls", "skipped_calls", "missing_terminal_calls",
              "decision_p50_ms", "decision_p95_ms", "wall_p50_ms", "wall_p95_ms", "latency_samples",
              "decision_cost_usd_known", "unknown_cost_calls", "request_count", "request_count_complete"]
    with (output / "metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for group in summary["groups"]:
            flattened = {f"{metric}_{name}": value for metric in ("boundary", "segment")
                         for name, value in group.get(metric, {}).items()}
            writer.writerow({**group, **flattened})
    is_demo = kind == "demonstration"
    is_real_pilot = kind == REAL_ACCURACY_PILOT
    if is_real_pilot:
        title = "Real-document accuracy pilot"
        introduction = (
            "This is a curated convenience sample of complete, short English public-sector PDFs. "
            "The 40 authentic originals are scored individually for classification and reused exactly once across eight constructed packets. "
            "These are 40 unique sources and 48 task inputs; task results are separate and must not be pooled. "
            "Shared originals and issuer/template families create dependence. Annotation is agent-assisted; human review was not performed. "
            "The first measured pass determines quality. Failures, preparation errors, skipped work, and missing results remain unsuccessful in the frozen denominator. "
            "Classification changes by 2.5 percentage points per error; packet exact match changes by 12.5 points. "
            "Inferential intervals are omitted for this non-random sample. Latency quantiles are descriptive. "
            "This does not establish general production accuracy, scan/Office performance, or accuracy on naturally aggregated packets.")
    elif is_demo:
        title = "Real-document timing pilot"
        introduction = (
            "This is a real-document demonstration timing pilot, using one original document and one assembled packet of originals. "
            "Timed repetitions do not establish general speed or held-out accuracy. Source reuse for excluded warmups is intentional and recorded. "
            "Quality means agreement with the declared demo label/assembly on the first timed run. Failures count as unsuccessful.")
    else:
        title = "Jev document benchmark"
        introduction = ("These are measured client wall times on synthetic documents. Quality uses the first measured pass per unique source; "
                        "latency uses all successful measured repetitions. Failures and missing results count as unsuccessful.")
    lines = [f"# {title}", "", f"Run: `{manifest['run_id']}`. Recorded {manifest['started_at']}.", "",
             f"Status: **{status}**. Stop reason: `{json.dumps(manifest.get('stop_reason'))}`.", "", introduction, "",
             "| Task | Engine / model | Quality | Completed | Decision p50 / p95 | Samples | Known measured decision API cost |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for group in summary["groups"]:
        quality = group.get("accuracy", group.get("packet_exact_match"))
        count = group.get("correct_count", group.get("exact_packets", 0))
        label = "correct" if group["task"] == "classify" else "exact"
        quality_text = f"{count}/{group['planned_unique']} source matches" if is_demo else f"{count}/{group['planned_unique']} {label} ({number(100*quality if quality is not None else None)}%)"
        lines.append(f"| {group['task']} | {group['engine']} / {group['model']} | {quality_text} | {group['completed_unique']}/{group['planned_unique']} | {number(group['decision_p50_ms'])} / {number(group['decision_p95_ms'])} ms | {group['latency_samples']} | ${group['decision_cost_usd_known']:.6f} ({group['unknown_cost_calls']} unknown-cost calls) |")
    lines += ["", "## Completion and failures", "",
              "Latency includes only successful complete invocations. Missing values are unavailable, never zero latency.", "",
              "| Task / engine | Planned | Dispatched | Successful | Failed / invalid | Skipped | Missing terminal |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for group in summary["groups"]:
        lines.append(f"| {group['task']} / {group['engine']} | {group['planned_calls']} | {group['dispatched_calls']} | {group['successful_calls']} | {group['failed_calls']} | {group['skipped_calls']} | {group['missing_terminal_calls']} |")
    lines += ["", f"Unclosed or contradictory dispatches: {summary['unclosed_dispatches']}. Their usage may be unknown; provider-request counts are incomplete when indicated. A start event does not establish that the provider stopped processing or charging.", "",
              "## OCR, warmups, and measured work", "",
              f"Configured warmups per engine/task: {config.get('warmups', 'unknown')}. Actual warmup invocations dispatched: {warmup['dispatched_calls']}; terminal records: {warmup['recorded_calls']}; successful: {warmup['successful_calls']}.", "",
              f"Preparation: {prep['items']} task-input artifacts, {prep['successful_items']} successful, {prep['failed_or_skipped_items']} failed/skipped, {prep['cache_hits']} cache hits. Each preparation is counted once across engines. Cached preparation is not a cold OCR measurement.", "",
              "| Component | Recorded wall time | Known estimated API cost | Unknown-cost observations |",
              "|---|---:|---:|---:|",
              f"| OCR preparation | {number(prep['wall_ms_known'] if prep['wall_samples'] else None)} ms ({prep['wall_samples']} timed inputs) | ${prep['cost_usd_known']:.6f} | {prep['unknown_cost_items']} |",
              f"| Excluded warmup decisions | {number(warmup['wall_ms_known'])} ms | ${warmup['decision_cost_usd_known']:.6f} | {warmup['unknown_cost_calls']} |",
              f"| Measured decisions | {number(measured['wall_ms_known'])} ms | ${measured['decision_cost_usd_known']:.6f} | {measured['unknown_cost_calls']} |",
              "", f"Known preparation conversion: {number(prep['conversion_ms_known'])} ms; OCR: {number(prep['ocr_ms_known'])} ms. These stage sums are separate from decision latency. LiteParse API cost is zero; local compute cost is not estimated.", "",
              f"Full-run known estimated API cost: **${known_total:.6f}**, including warmups and OCR. Unknown-cost observations: {unknown_total}. " + ("This known total is a lower bound." if unknown_total else "Infrastructure costs and account discounts are excluded."), ""]
    if embedded_ocr:
        lines += [f"OCR recorded inside task invocations: ${summary['components']['task_ocr']['cost_usd_known']:.6f} known, {summary['components']['task_ocr']['unknown_cost_requests']} unknown-cost requests; included once in the full-run total.", ""]
    pricing = manifest.get("pricing_snapshot")
    lines += ["## Scope and settings", "",
              f"- Scope: `{config['scope']}`. Concurrency: {config['concurrency']}. Repeats: {config['repeats']}.",
              "- Decision-only comparisons share exactly the same normalized OCR artifact. Their task wall time excludes OCR. End-to-end scope reports fresh OCR plus decisions in task wall time separately.",
              "- The LLM baseline returns whole-packet segments efficiently in one call when supported. Jev uses page category/boundary questions and bounded windows. This is a practical task comparison; no matched-decision comparison is claimed.",
              "- SDK retries are disabled. Provider caching and network variability are uncontrolled; cached-input/write tokens are reported separately. Separate process-cold startup is not measured.",
              f"- The local ${config['budget_usd']:g} reservation guard is an estimate, not a provider billing cap. Recorded retained unknown-cost reservations: ${summary['budget'].get('unknown_cost_reservations_usd', 0):.6f}. Separately, unclosed-start reservations are ${warmup['unclosed_dispatch_reservations_usd'] + measured['unclosed_dispatch_reservations_usd']:.6f}; these may overlap the recorded guard balance.",
              f"- Price snapshot: {pricing.get('date', 'date unavailable') if pricing else 'see frozen pricing hash and request records in manifest; no dated price object was recorded for this legacy run'}. USD figures use list-price estimates and reported usage; unknown usage stays unknown."]
    if not is_real_pilot:
        lines.append("- Bootstrap intervals resample unique sources, not repetitions. A one-source demonstration has no meaningful uncertainty estimate or general accuracy claim. Small-corpus results do not establish production accuracy.")
    lines += ["", "## Quality details", ""]
    for group in summary["groups"]:
        lines += [f"### {group['task']} / {group['engine']}", ""]
        if group["task"] == "classify":
            lines += [f"Macro-F1: {number(group['macro_f1'], 4)}. Correct: {group['correct_count']}/{group['total_count']}.", "",
                      "| Category | Support | Precision | Recall | F1 |", "|---|---:|---:|---:|---:|"]
            for category, values in group["per_class"].items():
                lines.append(f"| {category} | {values['support']} | {number(values['precision'], 4)} | {number(values['recall'], 4)} | {number(values['f1'], 4)} |")
            if not is_real_pilot:
                interval = group["accuracy_95pct_bootstrap"]
                lines += ["", f"Accuracy bootstrap 95% interval: {interval if interval is not None else 'not estimable with fewer than two unique sources'}."]
        else:
            lines += [f"Exact packets: {group['exact_packets']}/{group['total_packets']}; valid coverage: {group['coverage_valid_packets']}/{group['total_packets']}. Page accuracy: {number(group['page_accuracy'], 4)} ({group['page_correct_count']}/{group['page_total_count']}); page macro-F1: {number(group['page_macro_f1'], 4)}. Page metrics weight longer originals more heavily.", ""]
            for name in ("boundary", "segment"):
                values = group[name]
                lines += [f"{name.capitalize()} precision / recall / F1: {number(values['precision'], 4)} / {number(values['recall'], 4)} / {number(values['f1'], 4)}; matches {values['true_positive']}, predicted {values['predicted']}, actual {values['actual']}.", ""]
            lines += [f"Same-category boundary recall: {number(group['same_category_boundary_recall'], 4)} ({group['same_category_boundaries_found']}/{group['same_category_boundaries_actual']}).", ""]
            if not is_real_pilot:
                interval = group["packet_exact_match_95pct_bootstrap"]
                lines += [f"Packet exact-match bootstrap 95% interval: {interval if interval is not None else 'not estimable with fewer than two unique packets'}.", ""]
        repeat = "not measured (one pass)" if group["repeat_disagreement_status"] == "not_measured" else str(group["repeat_disagreement_documents"]) + " source(s)"
        lines += ["", f"Successful task-wall p50 / p95: {number(group['wall_p50_ms'])} / {number(group['wall_p95_ms'])} ms, n={group['wall_latency_samples']}.",
                  f"Reported measured decision input: {group['input_tokens_known']:,} tokens, including {group['cached_input_tokens_known']:,} cached-input tokens and {group['cache_write_tokens_known']:,} cache-write tokens. Provider caches can materially change costs.",
                  f"Reported decision requests: {group['request_count']} ({'complete' if group['request_count_complete'] else 'incomplete count'}). Failed or incorrect first-pass IDs: {', '.join(group['failures_or_incorrect_ids']) or 'none'}. Repeated-run disagreement: {repeat}. Error types: `{json.dumps(group['error_types'])}`. Skip reasons: `{json.dumps(group['skip_reasons'])}`.", ""]
    lines += ["Full confusion matrices, frozen denominators, ledgers, and per-item results are in `summary.json`, `metrics.csv`, `raw.jsonl`, and `manifest.json`. Where present, `events.jsonl` preserves dispatch starts and the preparation receipt preserves input identity. Reports regenerate offline from these records.", ""]
    (output / "report.md").write_text("\n".join(lines))
    _latency_chart(output, summary["groups"], {**config, "demo_set": summary["demo_set"]})
    return summary


def _latency_chart(output: Path, groups: list[dict], config: dict) -> None:
    maximum = max([group["decision_p95_ms"] or 0 for group in groups] + [1])
    height = 210 + len(groups) * 92
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}">',
           '<rect width="100%" height="100%" fill="#F5F5F5"/>',
           '<text x="45" y="55" font-family="Arial,sans-serif" font-size="30" fill="#000">Measured decision latency</text>',
           '<text x="45" y="85" font-family="Arial,sans-serif" font-size="16" fill="#737373">Successful whole document / packet · p50 / p95 · milliseconds</text>',
           f'<text x="45" y="111" font-size="14" fill="#737373">{html.escape(config.get("demo_set", "synthetic"))} · {html.escape(config.get("ocr", "liteparse"))} OCR · decision stage only · provider caches uncontrolled</text>']
    font = Path(__file__).resolve().parents[1] / "src/jev_docs/web/static/assets/brand/fonts/OverusedGrotesk-Regular.ttf"
    if font.is_file():
        encoded = base64.b64encode(font.read_bytes()).decode()
        svg.insert(1, f'<defs><style>@font-face{{font-family:OverusedGrotesk;src:url(data:font/ttf;base64,{encoded})}}text{{font-family:OverusedGrotesk,sans-serif}}</style></defs>')
    for index, group in enumerate(groups):
        y = 150 + index * 92
        color = "#3E18F9" if group["engine"] == "jev" else "#4B72FE"
        p50, p95 = group["decision_p50_ms"], group["decision_p95_ms"]
        label = html.escape(f"{group['task']} / {group['engine']}")
        svg.extend([f'<text x="45" y="{y+15}" font-size="18">{label}</text>',
                    f'<text x="45" y="{y+35}" font-size="13" fill="#737373">{html.escape(group["model"])}</text>',
                    f'<text x="45" y="{y+55}" font-size="11" fill="#737373">{group["planned_unique"]} inputs; n={group["latency_samples"]}; {group["failed_calls"]} failed; {group["skipped_calls"]} skipped; {group["missing_terminal_calls"]} missing</text>'])
        if p50 is not None and p95 is not None:
            svg.extend([f'<rect x="330" y="{y}" width="{p95/maximum*630:.1f}" height="28" fill="{color}" opacity="0.20"/>',
                        f'<rect x="330" y="{y}" width="{p50/maximum*630:.1f}" height="28" fill="{color}"/>'])
        svg.append(f'<text x="990" y="{y+20}" font-size="16">{number(p50)} / {number(p95)}</text>')
    svg.append('</svg>')
    (output / "latency.svg").write_text("\n".join(svg))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    write_report(parser.parse_args().output)

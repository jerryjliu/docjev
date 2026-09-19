"""Generate a shareable report from recorded observations, without provider calls."""

from __future__ import annotations

import argparse
import base64
import csv
import html
import json
from pathlib import Path

from .metrics import summarize


def number(value: float | None, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}" if value is not None else "n/a"


def write_report(output: Path) -> dict:
    manifest = json.loads((output / "manifest.json").read_text())
    observations = [json.loads(line) for line in (output / "raw.jsonl").read_text().splitlines() if line]
    summary = summarize(observations, manifest["datasets"])
    summary["run_id"] = manifest["run_id"]
    summary["config"] = manifest["config"]
    summary["demo_set"] = manifest.get("demo_set", "synthetic")
    summary["experiment_kind"] = manifest.get("experiment_kind", "heldout-synthetic-benchmark")
    summary["started_at"] = manifest["started_at"]
    summary["run_status"] = manifest.get("status", "unknown")
    summary["budget"] = manifest.get("budget", {})
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    fields = ["task", "engine", "model", "scope", "concurrency", "planned_unique", "completed_unique",
              "completion_rate", "accuracy", "packet_exact_match", "page_accuracy", "decision_p50_ms",
              "decision_p95_ms", "wall_p50_ms", "wall_p95_ms", "latency_samples", "failed_calls",
              "decision_cost_usd_known", "unknown_cost_calls"]
    with (output / "metrics.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary["groups"])
    is_demo = summary["experiment_kind"] == "demonstration"
    introduction = (
        "This is a real-document demonstration timing pilot, using one original document and one assembled packet of originals. Three timed repetitions do not establish general speed or held-out accuracy. Source reuse for excluded warmups is intentional and recorded. Quality below means agreement with the declared demo label/assembly on the first timed run."
        if is_demo else "These are measured client wall times on synthetic documents. Quality uses the first measured pass per unique source; latency uses all successful measured repetitions."
    )
    lines = ["# Real-document timing pilot" if is_demo else "# Jev document benchmark", "", f"Run: `{manifest['run_id']}`. Recorded {manifest['started_at']}.", "",
             introduction + " Failures count as unsuccessful. Missing pages count against page recall. Warmups are excluded from this table.", "",
             "| Task | Engine / model | Quality | Completed | Decision p50 / p95 | Samples | Known decision API cost |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for group in summary["groups"]:
        quality = group.get("accuracy", group.get("packet_exact_match"))
        label = "accuracy" if group["task"] == "classify" else "packet exact match"
        correct_count = round(quality * group["planned_unique"]) if quality is not None else 0
        quality_text = f"{correct_count}/{group['planned_unique']} source matches" if is_demo else f"{number(100*quality if quality is not None else None)}% {label}"
        lines.append(f"| {group['task']} | {group['engine']} / {group['model']} | {quality_text} | {group['completed_unique']}/{group['planned_unique']} | {number(group['decision_p50_ms'])} / {number(group['decision_p95_ms'])} ms | {group['latency_samples']} | ${group['decision_cost_usd_known']:.6f} ({group['unknown_cost_calls']} unknown-cost calls) |")
    lines += ["", "## Scope and settings", "", f"- Scope: `{manifest['config']['scope']}`. Concurrency: {manifest['config']['concurrency']}. Repeats: {manifest['config']['repeats']}. Warmups per engine/task: {manifest['config']['warmups']}.",
              "- Decision-only comparisons share exactly the same normalized OCR artifact. Their wall time measures only the task call; OCR is excluded. End-to-end scope starts from raw documents with local and remote OCR cache disabled and reports measured wall time separately.",
              "- The LLM baseline returns whole-packet segments efficiently in one call when supported. Jev uses page category/boundary questions and bounded windows. This is a practical task comparison; no matched-decision comparison is claimed.",
              "- SDK retries are disabled; request counts include all reported attempts. Provider cache state and network variability are not controlled. Separate process-cold startup is not measured by this run.",
              f"- USD figures use versioned list prices and reported tokens/credits. Unknown usage stays unknown; the local ${manifest['config']['budget_usd']:g} reservation guard is an estimate, not a provider billing cap.",
             "- Bootstrap intervals resample unique sources, not repetitions. A one-source demonstration has no meaningful uncertainty estimate or general accuracy claim. Small-corpus results do not establish production accuracy or latency across deployments.", "", "## Quality details", ""]
    for group in summary["groups"]:
        lines += [f"### {group['task']} / {group['engine']}", ""]
        if group["task"] == "classify":
            interval = group["accuracy_95pct_bootstrap"]
            lines += [f"Macro-F1: {number(group['macro_f1'], 4)}. Accuracy bootstrap 95% interval: {interval if interval is not None else 'not estimable with fewer than two unique sources'}.", ""]
        else:
            interval = group["packet_exact_match_95pct_bootstrap"]
            lines += [f"Page accuracy: {number(group['page_accuracy'], 4)}; page macro-F1: {number(group['page_macro_f1'], 4)}. Boundary F1: {number(group['boundary']['f1'], 4)}; exact category+range segment F1: {number(group['segment']['f1'], 4)}. Same-category boundary recall: {number(group['same_category_boundary_recall'], 4)}. Packet exact-match bootstrap 95% interval: {interval if interval is not None else 'not estimable with fewer than two unique packets'}.", ""]
        lines += [f"Reported measured decision input: {group['input_tokens_known']:,} tokens, including {group['cached_input_tokens_known']:,} cached-input tokens and {group['cache_write_tokens_known']:,} cache-write tokens. Provider caches can materially change this repeated-input cost comparison.", ""]
        lines += [f"Failed or incorrect first-pass IDs: {', '.join(group['failures_or_incorrect_ids']) or 'none'}. Repeated-run disagreement: {group['repeat_disagreement_documents']} source(s). Error types: `{json.dumps(group['error_types'])}`.", ""]
    lines += ["Full per-class confusion matrices, first-pass denominators, and request/cost details are in `summary.json`, `metrics.csv`, `raw.jsonl`, and `manifest.json`. The manifest freezes input hashes, prompt-source hashes, parser settings, and machine/package versions.", ""]
    (output / "report.md").write_text("\n".join(lines))
    _latency_chart(output, summary["groups"], manifest["config"])
    return summary


def _latency_chart(output: Path, groups: list[dict], config: dict) -> None:
    maximum = max([group["decision_p95_ms"] or 0 for group in groups] + [1])
    height = 210 + len(groups) * 92
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}">',
           '<rect width="100%" height="100%" fill="#F5F5F5"/>',
           '<text x="45" y="55" font-family="Arial,sans-serif" font-size="30" fill="#000">Measured decision latency</text>',
           '<text x="45" y="85" font-family="Arial,sans-serif" font-size="16" fill="#737373">Whole document / packet · bars: p50 · lighter extent: p95 · milliseconds</text>',
           f'<text x="45" y="111" font-size="14" fill="#737373">{html.escape(config.get("demo_set", "synthetic"))} · {html.escape(config.get("ocr", "liteparse"))} OCR · decision stage only · provider caches uncontrolled</text>']
    font = Path(__file__).resolve().parents[1] / "src/jev_docs/web/static/assets/brand/fonts/OverusedGrotesk-Regular.ttf"
    if font.is_file():
        encoded = base64.b64encode(font.read_bytes()).decode()
        svg.insert(1, f'<defs><style>@font-face{{font-family:OverusedGrotesk;src:url(data:font/ttf;base64,{encoded})}}text{{font-family:OverusedGrotesk,sans-serif}}</style></defs>')
    for index, group in enumerate(groups):
        y = 150 + index * 92
        color = "#3E18F9" if group["engine"] == "jev" else "#4B72FE"
        p50, p95 = group["decision_p50_ms"] or 0, group["decision_p95_ms"] or 0
        label = html.escape(f"{group['task']} / {group['engine']}")
        svg.extend([f'<text x="45" y="{y+15}" font-family="Arial,sans-serif" font-size="18">{label}</text>',
                    f'<text x="45" y="{y+35}" font-size="13" fill="#737373">{html.escape(group["model"])}</text>',
                    f'<text x="45" y="{y+55}" font-size="12" fill="#737373">{group["planned_unique"]} source(s), n={group["latency_samples"]}, concurrency {group["concurrency"]}</text>',
                    f'<rect x="280" y="{y}" width="{p95/maximum*690:.1f}" height="28" fill="{color}" opacity="0.20"/>',
                    f'<rect x="280" y="{y}" width="{p50/maximum*690:.1f}" height="28" fill="{color}"/>',
                    f'<text x="990" y="{y+20}" font-family="Arial,sans-serif" font-size="16">{p50:.1f} / {p95:.1f}</text>'])
    svg.append('</svg>')
    (output / "latency.svg").write_text("\n".join(svg))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    write_report(parser.parse_args().output)

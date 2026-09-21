"""Build the public visual report from the recorded run, entirely offline.

Usage: uv run python scripts/build_visual_report.py

This renderer never imports a decision engine, reads private OCR artifacts, or
performs inference. Its inputs are the committed evidence and original PDFs.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import mimetypes
import shutil
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

import pypdfium2 as pdfium

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "benchmarks/results/real-small-v1-run01"
CORPUS = ROOT / "datasets/real-small/v1"
OUTPUT = ROOT / "docs/report"
BRAND = ROOT / "src/jev_docs/web/static/assets/brand"
REPOSITORY = "https://github.com/jerryjliu/docjev"
ENGINES = ("jev", "openai")
CATEGORIES = {
    "tax_form": "Tax forms",
    "financial_report": "Financial reports",
    "press_release": "Press releases",
    "legal_notice": "Legal notices",
    "other": "Other",
}
THUMBNAILS = {
    "tax_form": ("e001", 1),
    "financial_report": ("e013", 1),
    "press_release": ("e019", 1),
    "legal_notice": ("e029", 1),
    "other": ("e033", 1),
    "error_before": ("e017", 2),
    "error_after": ("e017", 3),
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def github(path: str, *, page: int | None = None) -> str:
    return f"{REPOSITORY}/blob/main/{path}" + (f"#page={page}" if page else "")


def same_number(actual: float, expected: float) -> None:
    if not math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-10):
        raise ValueError(f"Recorded evidence does not reconcile: {actual} != {expected}")


def compact_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"category": item["category"], "pages": item["pages"]} for item in segments]


def compact_result(row: dict[str, Any]) -> dict[str, Any]:
    result = row["result"]
    metrics = result["metrics"]
    return {
        "status": row["status"],
        "decision_ms": metrics["decision_ms"],
        "wall_ms": row["wall_ms"],
        "cost_usd": metrics["decision_cost_usd"],
        "request_count": len(row["requests"]),
    }


def build_data() -> dict[str, Any]:
    summary = read_json(RESULT / "summary.json")
    manifest = read_json(RESULT / "manifest.json")
    preparation = read_json(RESULT / "preparation.json")
    sources = {item["id"]: item for item in read_json(CORPUS / "SOURCE.json")["sources"]}
    classify_truth = [
        item for item in read_json(CORPUS / "manifests/classify.json") if item["split"] == "test"
    ]
    split_truth = [
        item for item in read_json(CORPUS / "manifests/split.json") if item["split"] == "test"
    ]
    all_rows = [json.loads(line) for line in (RESULT / "raw.jsonl").read_text().splitlines()]
    rows = [row for row in all_rows if row["phase"] == "measured"]
    index = {(row["task"], row["source_id"], row["engine"]): row for row in rows}
    if len(index) != 96 or len(rows) != 96 or len(all_rows) != 100:
        raise ValueError("This report requires the complete, unique 96-call measured run.")
    if any(row["status"] != "ok" or row["usage_unknown"] for row in all_rows):
        raise ValueError("This report requires the recorded complete run with known cost estimates.")
    if summary["run_status"] != "complete" or len(classify_truth) != 40 or len(split_truth) != 8:
        raise ValueError("Unexpected run or corpus shape.")
    if Counter(item["category"] for item in classify_truth) != dict.fromkeys(CATEGORIES, 8):
        raise ValueError("Unexpected category balance.")
    for source in sources.values():
        if hashlib.sha256((ROOT / source["path"]).read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError(f"Original source bytes changed: {source['id']}")

    classifications = []
    for item in classify_truth:
        source = sources[item["id"]]
        results = {}
        pair = [index[("classify", item["id"], engine)] for engine in ENGINES]
        if pair[0]["parsed_pages_sha256"] != pair[1]["parsed_pages_sha256"]:
            raise ValueError("Engines did not receive identical parsed classification pages.")
        for engine, row in zip(ENGINES, pair, strict=True):
            prediction = row["result"]
            results[engine] = {
                **compact_result(row),
                "category": prediction["category"],
                "correct": prediction["category"] == item["category"],
                "needs_review": prediction["needs_review"],
            }
        classifications.append({
            "id": item["id"],
            "title": source["title"],
            "issuer": source["issuer"],
            "category": item["category"],
            "pages": item["page_count"],
            "source_url": source["source_url"],
            "repo_path": source["path"],
            "repo_relative_url": "../../" + source["path"],
            "github_url": github(source["path"]),
            "results": results,
        })

    packets = []
    for item in split_truth:
        truth = compact_segments(item["segments"])
        results = {}
        pair = [index[("split", item["id"], engine)] for engine in ENGINES]
        if pair[0]["parsed_pages_sha256"] != pair[1]["parsed_pages_sha256"]:
            raise ValueError("Engines did not receive identical parsed splitting pages.")
        for engine, row in zip(ENGINES, pair, strict=True):
            segments = compact_segments(row["result"]["segments"])
            results[engine] = {
                **compact_result(row),
                "segments": segments,
                "exact": segments == truth,
            }
        packets.append({
            "id": item["id"],
            "pages": item["page_count"],
            "source_ids": item["source_ids"],
            "truth": [
                {**segment, "source_id": source_id, "title": sources[source_id]["title"]}
                for segment, source_id in zip(truth, item["source_ids"], strict=True)
            ],
            "source_page_mapping": item["source_page_mapping"],
            "repo_path": item["path"],
            "repo_relative_url": "../../" + item["path"],
            "github_url": github(item["path"]),
            "results": results,
        })

    fields = {
        "model", "correct_count", "total_count", "accuracy", "macro_f1",
        "decision_p50_ms", "decision_p95_ms", "wall_p50_ms", "wall_p95_ms",
        "latency_samples", "decision_cost_usd_known", "unknown_cost_calls", "request_count",
        "exact_packets", "total_packets", "packet_exact_match", "coverage_validity",
        "page_correct_count", "page_total_count", "page_accuracy", "boundary", "segment",
        "same_category_boundaries_found", "same_category_boundaries_actual",
        "needs_review_rate", "successful_calls", "failed_calls", "skipped_calls",
    }
    tasks: dict[str, Any] = {}
    for task, items in (("classify", classifications), ("split", packets)):
        groups = {group["engine"]: group for group in summary["groups"] if group["task"] == task}
        task_data: dict[str, Any] = {
            engine: {k: v for k, v in groups[engine].items() if k in fields} for engine in ENGINES
        }
        for engine in ENGINES:
            correct_field = "correct" if task == "classify" else "exact"
            expected_field = "correct_count" if task == "classify" else "exact_packets"
            if sum(item["results"][engine][correct_field] for item in items) != groups[engine][expected_field]:
                raise ValueError("Raw predictions do not reconcile with summary accuracy.")
            same_number(median(item["results"][engine]["decision_ms"] for item in items), groups[engine]["decision_p50_ms"])
            same_number(sum(item["results"][engine]["cost_usd"] for item in items), groups[engine]["decision_cost_usd_known"])
        task_data["ratio_of_medians"] = groups["openai"]["decision_p50_ms"] / groups["jev"]["decision_p50_ms"]
        task_data["paired_median_speedup"] = median(
            item["results"]["openai"]["decision_ms"] / item["results"]["jev"]["decision_ms"] for item in items
        )
        task_data["paired_count"] = len(items)
        tasks[task] = task_data

    costs: dict[str, Any] = {}
    for engine in ENGINES:
        engine_rows = [row for row in all_rows if row["engine"] == engine]
        measured = sum(row["result"]["metrics"]["decision_cost_usd"] for row in engine_rows if row["phase"] == "measured")
        warmup = sum(row["result"]["metrics"]["decision_cost_usd"] for row in engine_rows if row["phase"] == "warmup")
        costs[engine] = {"measured_usd": measured, "warmup_usd": warmup, "total_usd": measured + warmup}
    total = sum(costs[engine]["total_usd"] for engine in ENGINES)
    same_number(total, summary["accounting"]["full_run_cost_usd_known"])
    costs.update({
        "total_usd": total,
        "measured_usd": summary["components"]["measured"]["decision_cost_usd_known"],
        "warmup_usd": summary["components"]["warmup"]["decision_cost_usd_known"],
        "ocr_api_usd": 0,
        "local_compute_cost": "not estimated",
        "status": "estimated from recorded provider usage and the saved pricing snapshot",
        "unknown_cost_calls": summary["accounting"]["unknown_cost_observations"],
        "pricing_date": summary["pricing_snapshot"]["date"],
        "pricing_sources": summary["pricing_snapshot"]["sources"],
        "budget_usd": manifest["budget"]["limit_usd"],
    })
    p001 = next(item for item in packets if item["id"] == "p001")
    if not p001["results"]["openai"]["exact"] or p001["results"]["jev"]["exact"]:
        raise ValueError("The recorded error case changed.")

    return {
        "schema_version": 1,
        "run": {
            "id": summary["run_id"], "date": summary["started_at"][:10],
            "status": summary["run_status"], "originals": 40, "packets": 8,
            "unique_pages": sum(item["pages"] for item in classifications),
            "categories": 5, "documents_per_category": 8, "measured_calls": 96,
            "warmup_calls": 4, "seed": manifest["config"]["seed"],
        },
        "categories": [{"id": key, "label": label, "count": 8} for key, label in CATEGORIES.items()],
        "engines": {
            "jev": {"label": "Jev", "model": "jev-1.13.0"},
            "openai": {"label": "GPT-5.6 Luna", "model": "gpt-5.6-luna"},
        },
        "tasks": tasks,
        "classifications": classifications,
        "packets": packets,
        "costs": costs,
        "stages": {
            "preparation_seconds": preparation["elapsed_seconds"],
            "paid_seconds": manifest["paid_elapsed_seconds"],
            "measured_seconds": manifest["measured_elapsed_seconds"],
            "run_seconds": manifest["elapsed_seconds"],
            "warmup_call_seconds": summary["components"]["warmup"]["wall_ms_known"] / 1000,
            "preparation_items": summary["components"]["preparation"]["items"],
            "preparation_cache_hits": summary["components"]["preparation"]["cache_hits"],
            "note": "Preparation is shared once. Paid-stage elapsed time includes four excluded warmups; run time also includes setup and cleanup. Stages omit the manual pause between preparation and inference.",
        },
        "error": {
            "packet_id": "p001", "source_id": "e017",
            "title": "The attachment that looked like a new document",
            "source_title": sources["e017"]["title"],
            "expected_packet_pages": [7, 8, 9, 10],
            "predicted_packet_segments": [[7, 8], [9, 10]],
            "extra_boundary_after_packet_page": 8,
            "before_source_page": 2, "after_source_page": 3,
            "source_url": sources["e017"]["source_url"],
            "github_url": github(sources["e017"]["path"]),
            "explanation": "Jev split the FOMC statement from its implementation attachment. Both pieces kept the correct press-release label. The frozen rules retain supporting attachments with their original publication; GPT-5.6 Luna preserved the expected segment.",
            "interpretation": "The new heading and repeated release timestamp plausibly explain the extra boundary; this is an inference from layout, not access to model reasoning.",
        },
        "methodology": {
            "comparison": "Practical task implementations, using identical cached LiteParse text for each matched input.",
            "latency": "Decision latency per complete document or packet, excluding OCR and four warmups. Headline speed ratios divide Luna's median by Jev's median over the same source set.",
            "accuracy": "Classification counts a correct category; exact splitting requires every labeled segment and page boundary to match the frozen publication-based truth.",
            "protocol": "One measured pass, concurrency 1, seeded paired provider order, zero retries, fixed rules and thresholds. No provider-cache control or repeatability measurement.",
            "sampling": "40 curated English government PDFs, not a representative production sample. Eight constructed packets reuse the same 40 originals, with no separator pages. The two tasks are not independent datasets.",
            "annotation": "Agent labels plus separate agent review before inference. Independent human review was not performed.",
            "coverage": "Digital PDFs and blank official tax forms; no evidence here for filled private forms, scans, other languages, or general office formats.",
            "uncertainty": "No headline confidence intervals: curated sample, source overlap, and shared issuer templates limit generalization.",
            "other": "Other is an explicit catch-all category. Both engines flag all eight Other documents for review even when the category is correct.",
            "no_endorsement": "Source agencies and organizations do not sponsor or endorse this independent evaluation.",
        },
        "links": {
            "repository": REPOSITORY,
            "report": github("benchmarks/results/real-small-v1-run01/report.md"),
            "raw": github("benchmarks/results/real-small-v1-run01/raw.jsonl"),
            "summary": github("benchmarks/results/real-small-v1-run01/summary.json"),
            "methodology": github("docs/benchmark-methodology.md"),
            "dataset_card": github("datasets/real-small/v1/DATASET_CARD.md"),
            "source_manifest": github("datasets/real-small/v1/SOURCE.json"),
            "error_analysis": github("benchmarks/results/real-small-v1-run01/error-analysis.md"),
            "freeze": github("datasets/real-small/v1/FREEZE.json"),
        },
        "evidence_sha256": {
            name: hashlib.sha256((RESULT / name).read_bytes()).hexdigest()
            for name in ("summary.json", "raw.jsonl", "manifest.json", "preparation.json")
        },
    }


def data_url(path: Path, media_type: str) -> str:
    return f"data:{media_type};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def build_assets() -> dict[str, str]:
    directory = OUTPUT / "assets"
    directory.mkdir(parents=True, exist_ok=True)
    assets: dict[str, str] = {}
    asset_manifest = {}
    previews = dict(THUMBNAILS)
    for source in read_json(CORPUS / "SOURCE.json")["sources"]:
        document = pdfium.PdfDocument(ROOT / source["path"])
        try:
            previews.update({f"page_{source['id']}_{number}": (source["id"], number)
                             for number in range(1, len(document) + 1)})
        finally:
            document.close()
    rendered_pages: dict[tuple[str, int], str] = {}
    for key, (source_id, page_number) in previews.items():
        path = CORPUS / "originals" / f"{source_id}.pdf"
        destination = directory / f"{source_id}-page-{page_number}.jpg"
        identity = (source_id, page_number)
        if identity not in rendered_pages:
            document = pdfium.PdfDocument(path)
            try:
                page = document[page_number - 1]
                try:
                    bitmap = page.render(scale=1000 / page.get_width())
                    try:
                        rendered = bitmap.to_pil().convert("RGB")
                        rendered.save(destination, "JPEG", quality=85, optimize=True)
                    finally:
                        bitmap.close()
                finally:
                    page.close()
            finally:
                document.close()
            rendered_pages[identity] = f"assets/{destination.name}"
        assets[key] = rendered_pages[identity]
        asset_manifest[key] = {
            "source_id": source_id, "page": page_number,
            "file": destination.name, "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "transformation": "Complete original page, scaled raster rendering; no crop or content edits.",
        }
    for key, name in (
        ("font_regular", "OverusedGrotesk-Regular.ttf"),
        ("font_medium", "OverusedGrotesk-Medium.ttf"),
        ("font_mono", "IBMPlexMono-Regular.ttf"),
    ):
        shutil.copyfile(BRAND / "fonts" / name, directory / name)
        assets[key] = f"assets/{name}"
    for name in ("IBMPlexMono-OFL.txt", "OverusedGrotesk-LICENSE.txt"):
        shutil.copyfile(BRAND / "fonts" / name, directory / name)
        assets[name] = (BRAND / "fonts" / name).read_text()
    shutil.copyfile(BRAND / "llamaindex-wordmark-black.png", directory / "llamaindex-wordmark-black.png")
    assets["logo"] = "assets/llamaindex-wordmark-black.png"
    (directory / "manifest.json").write_text(json.dumps(asset_manifest, indent=2) + "\n")
    (directory / "NOTICE.md").write_text(
        "# Report assets\n\n"
        "Page previews are full-page raster renderings of the authentic originals in "
        "`datasets/real-small/v1/originals/`. They are scaled only; source content is not "
        "cropped or altered. `manifest.json` records original page numbers and PDF hashes. "
        "Source URLs and rights are recorded in `datasets/real-small/v1/SOURCE.json` and "
        "`NOTICE.md`. Official marks identify their sources; no endorsement is implied.\n\n"
        "LlamaIndex's unchanged wordmark and bundled fonts are copied from "
        "`src/jev_docs/web/static/assets/brand/`; see its `NOTICE.md` and `sources.json` "
        "for provenance. Font license notices are included beside the font files.\n"
    )
    return assets


def inline_json(value: Any) -> str:
    # Keep source titles from ever terminating an HTML script element.
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--standalone", type=Path, help="Also export a self-contained offline HTML to this path")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    data = build_data()
    assets = build_assets()
    (OUTPUT / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    template = OUTPUT / "template.html"
    if template.is_file():
        content = template.read_text()
        for placeholder in ("__REPORT_DATA__", "__REPORT_ASSETS__"):
            if content.count(placeholder) != 1:
                raise ValueError(f"Expected exactly one {placeholder} in template.html")
        content = content.replace("__REPORT_DATA__", inline_json(data))
        content = content.replace("__REPORT_ASSETS__", inline_json(assets))
        (OUTPUT / "index.html").write_text(content)
        if args.standalone:
            embedded = {
                key: data_url(OUTPUT / value, mimetypes.guess_type(value)[0] or "application/octet-stream")
                if value.startswith("assets/") else value for key, value in assets.items()
            }
            standalone = template.read_text().replace("__REPORT_DATA__", inline_json(data))
            standalone = standalone.replace("__REPORT_ASSETS__", inline_json(embedded))
            args.standalone.parent.mkdir(parents=True, exist_ok=True)
            args.standalone.write_text(standalone)
    print("Built offline report data and authentic page previews; no API calls.")
    print(json.dumps({
        "classify_ratio_of_medians": data["tasks"]["classify"]["ratio_of_medians"],
        "split_ratio_of_medians": data["tasks"]["split"]["ratio_of_medians"],
        "total_estimated_usd": data["costs"]["total_usd"],
    }, indent=2))


if __name__ == "__main__":
    main()

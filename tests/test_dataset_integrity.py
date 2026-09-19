"""Offline checks for the frozen first-party benchmark and separate demos."""
import hashlib
import json
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def manifest(name):
    return json.loads((ROOT / "datasets" / "manifests" / f"{name}.json").read_text())


def test_classification_balance_and_split_sizes():
    rows = manifest("classify")
    assert len(rows) == 60
    assert Counter(row["category"] for row in rows) == dict.fromkeys(
        ["invoice", "purchase_order", "contract", "resume", "pitch_deck", "other"], 10
    )
    assert Counter(row["split"] for row in rows) == {"dev": 12, "test": 48}
    assert all(count == 2 for count in Counter(row["category"] for row in rows if row["split"] == "dev").values())
    assert Counter(row["split"] for row in manifest("split")) == {"dev": 6, "test": 18}


def test_source_and_template_isolation():
    sources = set()
    for name in ("classify", "split"):
        families = {"dev": set(), "test": set()}
        for row in manifest(name):
            assert sources.isdisjoint(row["source_ids"])
            sources.update(row["source_ids"])
            families[row["split"]].add(row["template_family"])
        assert families["dev"].isdisjoint(families["test"])
    demo = json.loads((ROOT / "examples/demo-manifest.json").read_text())
    for row in demo["classify"] + demo["split"]:
        assert sources.isdisjoint(row["source_ids"])
        sources.update(row["source_ids"])


def test_file_hashes_page_counts_and_neutral_names():
    paths = set()
    for name in ("classify", "split"):
        for row in manifest(name):
            path = ROOT / row["path"]
            assert path not in paths
            paths.add(path)
            assert path.stem == row["id"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
            if row["format"] == "pdf":
                doc = PdfReader(path)
                assert len(doc.pages) == row["page_count"]
                assert doc.metadata.title == "Document"


def test_split_contiguous_complete_and_adjacent_same_category():
    for row in manifest("split"):
        segments = row["segments"]
        assert len(segments) == len(row["source_ids"])
        assert [p for segment in segments for p in segment["pages"]] == list(range(1, row["page_count"] + 1))
        assert all(segment["pages"] for segment in segments)
        assert any(a["category"] == b["category"] == "invoice" for a, b in zip(segments, segments[1:], strict=False))


def test_scan_inputs_are_really_image_only_and_formats_are_balanced():
    rows = manifest("classify")
    scanned = [row for row in rows if row["scan"]]
    assert len(scanned) == 12
    assert len({row["category"] for row in scanned}) == 6
    for row in scanned:
        assert not "".join(page.extract_text() for page in PdfReader(ROOT / row["path"]).pages).strip()
    assert len({row["category"] for row in rows if row["format"] == "docx"}) == 6


def test_demo_separation_and_formats():
    demo = json.loads((ROOT / "examples/demo-manifest.json").read_text())
    assert len(demo["classify"]) == 6
    assert {row["format"] for row in demo["classify"]} == {"pdf", "docx", "pptx"}
    frozen_hashes = {row["sha256"] for name in ("classify", "split") for row in manifest(name)}
    for row in demo["classify"] + demo["split"]:
        assert row["sha256"] not in frozen_hashes
        assert hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest() == row["sha256"]
    packet = demo["split"][0]
    assert packet["page_count"] == 9
    assert packet["segments"][3:5] == [
        {"category": "invoice", "pages": [6, 7]},
        {"category": "invoice", "pages": [8]},
    ]


def test_verified_blank_pages_are_in_ground_truth():
    blanks = 0
    for row in manifest("split"):
        pdf = PdfReader(ROOT / row["path"])
        labels = {number: segment["category"] for segment in row["segments"] for number in segment["pages"]}
        for number, page in enumerate(pdf.pages, 1):
            if not page.extract_text().strip() and not page.images:
                assert labels[number] == "other"
                blanks += 1
    assert blanks == 6


def test_format_variants_are_explicitly_related():
    rows = json.loads((ROOT / "examples/fixtures/manifest.json").read_text())
    assert {row["format"] for row in rows} == {"pdf", "docx", "pptx"}
    assert len({row["related_group"] for row in rows}) == 1
    for row in rows:
        assert row["excluded_from_accuracy"] is True
        assert row["page_count"] == 3
        assert hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest() == row["sha256"]

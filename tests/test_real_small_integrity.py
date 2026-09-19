"""Real corpus guarantees deliberately differ from the separate synthetic fixtures."""

from __future__ import annotations

import json
import runpy
import shutil
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[1]
API = runpy.run_path(str(ROOT / "datasets/real-small/prepare.py"))
VERIFY = API["verify_corpus"]
BASE = Path("datasets/real-small/v1")


@pytest.fixture
def corpus_copy(tmp_path):
    target = tmp_path / "repo"
    shutil.copytree(
        ROOT / "datasets/real-small",
        target / "datasets/real-small",
        ignore=shutil.ignore_patterns("qa", "__pycache__"),
    )
    shutil.copytree(ROOT / "examples/real", target / "examples/real")
    shutil.copy2(ROOT / "datasets/LICENSE", target / "datasets/LICENSE")
    return target


def edit_json(root, name, mutate):
    path = root / BASE / name
    value = json.loads(path.read_text())
    mutate(value)
    path.write_text(json.dumps(value))


def test_frozen_real_corpus_counts_and_every_rendered_page():
    result = VERIFY(ROOT, require_review=True, render=True)
    assert result["originals"] == result["classification_test_count"] == 40
    assert result["split_test_count"] == 8
    assert result["source_pages"] == 116
    assert result["task_input_pages"] == 232
    assert result["true_segments"] == 40
    assert result["true_boundaries"] == 32
    assert result["same_category_boundaries"] == 4
    assert result["adjacent_same_category_packets"] == 4
    assert max(result["packet_pages"]) <= 25
    assert result["excluded_warmup_inputs"] == 2
    assert result["excluded_warmup_task_invocations"] == 4
    assert result["freeze_sha256"]


def test_verification_is_offline_and_read_only(monkeypatch):
    import socket

    def network_forbidden(*args, **kwargs):
        raise AssertionError("verification attempted network access")

    monkeypatch.setattr(socket.socket, "connect", network_forbidden)
    paths = [ROOT / p for p in API["identity_paths"](ROOT)] + [ROOT / BASE / "FREEZE.json"]
    before = {p: (API["sha"](p), p.stat().st_mtime_ns) for p in paths}
    VERIFY(ROOT)
    assert before == {p: (API["sha"](p), p.stat().st_mtime_ns) for p in paths}


def test_duplicate_source_rejected(corpus_copy):
    def duplicate(data):
        data["packets"][0]["source_ids"][1] = data["packets"][0]["source_ids"][0]

    edit_json(corpus_copy, "packet-plan.json", duplicate)
    with pytest.raises(ValueError, match="Duplicate/missing packet sources"):
        VERIFY(corpus_copy)


def test_missing_page_mapping_rejected(corpus_copy):
    def drop_page(data):
        data[0]["source_page_mapping"][0]["source_pages"].pop()

    edit_json(corpus_copy, "manifests/split.json", drop_page)
    with pytest.raises(ValueError, match="Bad packet provenance"):
        VERIFY(corpus_copy)


def test_bad_label_rejected(corpus_copy):
    def bad_label(data):
        data["annotations"][0]["category"] = "unlisted"

    edit_json(corpus_copy, "annotations.json", bad_label)
    with pytest.raises(ValueError, match="five categories"):
        VERIFY(corpus_copy)


def test_unreviewed_source_rejected(corpus_copy):
    def unreview(data):
        data["annotations"][0]["review"]["status"] = "pending"

    edit_json(corpus_copy, "annotations.json", unreview)
    with pytest.raises(ValueError, match="Missing independent agent review"):
        VERIFY(corpus_copy)


def test_review_is_bound_to_exact_source_bytes(corpus_copy):
    def wrong_hash(data):
        data["annotations"][0]["review"]["source_sha256"] = "0" * 64

    edit_json(corpus_copy, "annotations.json", wrong_hash)
    with pytest.raises(ValueError, match="Missing independent agent review"):
        VERIFY(corpus_copy)


def test_no_new_or_scored_dev_examples(corpus_copy):
    def collide(data):
        data[-1]["id"] = "e001"

    edit_json(corpus_copy, "manifests/classify.json", collide)
    with pytest.raises(ValueError, match="globally unique"):
        VERIFY(corpus_copy)


def test_freeze_is_not_silently_updated(corpus_copy):
    path = corpus_copy / BASE / "rules/classify.yaml"
    path.write_text(path.read_text() + "\n# changed after freeze\n")
    frozen = corpus_copy / BASE / "FREEZE.json"
    before = frozen.read_bytes()
    with pytest.raises(ValueError, match="Frozen identity changed"):
        VERIFY(corpus_copy)
    assert frozen.read_bytes() == before


def test_changed_resources_detected_even_when_streams_match(tmp_path):
    original, changed = tmp_path / "original.pdf", tmp_path / "changed.pdf"
    canvas = Canvas(str(original), pagesize=(400, 200), invariant=1)
    canvas.setFont("Helvetica", 28)
    canvas.drawString(25, 100, "Different font width")
    canvas.save()
    writer = PdfWriter()
    writer.append(original)
    fonts = writer.pages[0]["/Resources"]["/Font"]
    font = next(iter(fonts.values())).get_object()
    font[NameObject("/BaseFont")] = NameObject("/Courier")
    writer.write(changed)
    assert API["page_signature"](PdfReader(original).pages[0]) == API["page_signature"](
        PdfReader(changed).pages[0]
    )
    API["assert_same_pages"](original, changed, [1], render=False)
    with pytest.raises(ValueError, match="Changed rendered page/resources"):
        API["assert_same_pages"](original, changed, [1], render=True)


def test_changed_original_bytes_rejected(corpus_copy):
    original = corpus_copy / BASE / "originals/e001.pdf"
    with original.open("ab") as stream:
        stream.write(b"\n% appended after review\n")
    with pytest.raises(ValueError, match="Changed source: e001"):
        VERIFY(corpus_copy)


def test_assembly_and_freeze_refuse_overwriting_frozen_version(corpus_copy):
    with pytest.raises(ValueError, match="Frozen corpus cannot be reassembled"):
        API["assemble"](corpus_copy)
    with pytest.raises(ValueError, match="Refusing to overwrite freeze"):
        API["freeze_corpus"](corpus_copy)

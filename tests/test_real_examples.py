"""Authentic demo inputs retain their exact source bytes and page provenance."""
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "examples" / "real"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_real_originals_match_download_provenance():
    sources = json.loads((HERE / "SOURCE.json").read_text())["sources"]
    demo = json.loads((HERE / "demo-manifest.json").read_text())
    assert len(sources) == len(demo["classify"]) == 5
    for source, entry in zip(sources, demo["classify"], strict=True):
        path = ROOT / source["path"]
        assert path.stem == source["id"] == entry["id"]
        assert digest(path.read_bytes()) == source["sha256"] == entry["sha256"]
        assert path.stat().st_size == source["byte_count"]
        assert source["source_url"].startswith("https://")
        assert source["rights"] == "public-domain-us-government"
        reader = PdfReader(path)
        assert len(reader.pages) == source["page_count"] == entry["page_count"]
        assert source["source_pages"] == list(range(1, len(reader.pages) + 1))
        assert [digest(p.get_contents().get_data()) for p in reader.pages] == source["page_content_sha256"]


def test_real_packet_preserves_every_source_page_and_boundary():
    sources = {s["id"]: s for s in json.loads((HERE / "SOURCE.json").read_text())["sources"]}
    demo = json.loads((HERE / "demo-manifest.json").read_text())
    entries = {e["id"]: e for e in demo["classify"]}
    packet = demo["split"][0]
    path = ROOT / packet["path"]
    assert digest(path.read_bytes()) == packet["sha256"]
    reader = PdfReader(path)
    assert len(reader.pages) == packet["page_count"] == 15
    assert packet["provenance_kind"] == "assembled"
    assert [p for m in packet["source_page_mapping"] for p in m["packet_pages"]] == list(range(1, 16))
    assert [m["source_id"] for m in packet["source_page_mapping"]] == packet["source_ids"]
    for mapping, segment in zip(packet["source_page_mapping"], packet["segments"], strict=True):
        source = sources[mapping["source_id"]]
        original = PdfReader(ROOT / source["path"])
        assert mapping["source_pages"] == list(range(1, source["page_count"] + 1))
        assert segment["pages"] == mapping["packet_pages"]
        assert segment["category"] == entries[source["id"]]["category"]
        for src_page, dst_page in zip(mapping["source_pages"], mapping["packet_pages"], strict=True):
            expected, actual = original.pages[src_page - 1], reader.pages[dst_page - 1]
            assert digest(actual.get_contents().get_data()) == source["page_content_sha256"][src_page - 1]
            assert expected.mediabox == actual.mediabox
    assert packet["segments"][1:3] == [
        {"category": "financial_report", "pages": [4]},
        {"category": "financial_report", "pages": [5]},
    ]

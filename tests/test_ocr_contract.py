"""Offline contract checks plus explicitly opted-in cloud smoke tests."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas

from jev_docs.documents import parse_document
from jev_docs.errors import DocumentError, ProviderError
from jev_docs.ocr import liteparse, llamaparse


def scan_pdf(path: Path) -> Path:
    images = []
    for number in (1, 2):
        image = Image.new("RGB", (1600, 1000), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=60)
        draw.text((90, 120), f"INVOICE 102{number}", font=font, fill="black")
        draw.text((90, 240), "Total due 250 dollars", font=font, fill="black")
        images.append(image)
    images[0].save(path, resolution=150, save_all=True, append_images=images[1:])
    for image in images:
        image.close()
    return path


def test_liteparse_scanned_multipage_pdf(tmp_path):
    parsed = parse_document(scan_pdf(tmp_path / "scan.pdf"), cache_dir=tmp_path / "cache", use_cache=False)
    assert parsed.page_count == 2
    assert "1021" in parsed.pages[0].text
    assert "1022" in parsed.pages[1].text
    assert all("250" in page.text for page in parsed.pages)
    assert parsed.metrics.ocr_cost_usd == 0
    assert parsed.parser.options["ocr_enabled"]


def test_liteparse_page_errors_not_silently_dropped(tmp_path, monkeypatch):
    import liteparse as sdk

    class Broken:
        def __init__(self, **_):
            pass

        def parse(self, _):
            return SimpleNamespace(page_errors=[SimpleNamespace(page_num=2)])

    monkeypatch.setattr(sdk, "LiteParse", Broken)
    with pytest.raises(DocumentError, match=r"page\(s\) 2"):
        liteparse.parse_pdf(tmp_path / "unused.pdf", 2)


@pytest.mark.parametrize("tier,expected", [("cost-effective", "cost_effective"),
                                          ("agentic", "agentic"), ("agentic-plus", "agentic_plus")])
def test_cloud_tiers_map_without_other_services(tier, expected):
    assert llamaparse.normalize_tier(tier) == expected


def test_unknown_tier_and_missing_credentials_fail(tmp_path, monkeypatch):
    with pytest.raises(DocumentError, match="tier"):
        llamaparse.normalize_tier("classify")
    monkeypatch.delenv("LLAMA_CLOUD_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="LLAMA_CLOUD_API_KEY"):
        llamaparse.parse_pdf(tmp_path / "unused.pdf", 1, tier="agentic", parser_version="latest")


def test_cloud_contract_headers_usage_and_no_retry(tmp_path, monkeypatch):
    import llama_cloud

    page = SimpleNamespace(page_number=1, success=True, header="Reference A", markdown="Body", footer="Page 1")
    response = SimpleNamespace(job=SimpleNamespace(status="COMPLETED", id="safe-job-id", usage=SimpleNamespace(credits=10)),
                               markdown=SimpleNamespace(pages=[page]), raw_parameters={"version": "2026-07-24"})
    calls = []

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            self.files = SimpleNamespace(create=self.upload)
            self.parsing = SimpleNamespace(parse=self.parse)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def upload(self, **kwargs):
            assert kwargs["purpose"] == "parse"
            assert kwargs["file"][0] == "document.pdf"
            return SimpleNamespace(id="file-1")

        def parse(self, **kwargs):
            calls.append(kwargs)
            return response

    monkeypatch.setattr(llama_cloud, "LlamaCloud", Client)
    monkeypatch.setenv("LLAMA_CLOUD_API_KEY", "test-only-secret")
    source = tmp_path / "source.pdf"
    source.write_bytes(b"fixture")
    result = llamaparse.parse_pdf(source, 1, tier="agentic", parser_version="latest", disable_cache=True)
    assert result.pages[0].text == "Reference A\n\nBody\n\nPage 1"
    assert result.parser.version == "2026-07-24"
    assert result.cost_usd == 0.0125 and result.cost_status == "estimated"
    assert calls[0]["disable_cache"] is True
    assert calls[0]["expand"] == ["markdown", "usage", "job_metadata"]
    response.job.usage = None
    result = llamaparse.parse_pdf(source, 1, tier="agentic", parser_version="latest")
    assert result.cost_usd is None and result.cost_status == "unknown"
    page.success = False
    with pytest.raises(DocumentError, match="failed on page"):
        llamaparse.parse_pdf(source, 1, tier="agentic", parser_version="latest")


def test_cloud_error_does_not_expose_provider_body(tmp_path, monkeypatch):
    import llama_cloud

    def fail(**_):
        raise RuntimeError("test-only-secret and private contents")

    monkeypatch.setenv("LLAMA_CLOUD_API_KEY", "test-only-secret")
    monkeypatch.setattr(llama_cloud, "LlamaCloud", fail)
    with pytest.raises(ProviderError) as error:
        llamaparse.parse_pdf(tmp_path / "unused.pdf", 1, tier="agentic", parser_version="latest")
    assert "test-only-secret" not in str(error.value)
    assert "private contents" not in str(error.value)


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("JEV_DOCS_LIVE_OCR") != "1", reason="Set JEV_DOCS_LIVE_OCR=1 to permit three paid one-page Parse calls")
@pytest.mark.parametrize("tier", ["cost-effective", "agentic", "agentic-plus"])
def test_live_llamaparse_tier(tmp_path, tier):
    source = tmp_path / "contract.pdf"
    document = canvas.Canvas(str(source), invariant=True)
    document.drawString(72, 720, "INVOICE 1024. Amount due 250 dollars.")
    document.showPage()
    document.save()
    parsed = parse_document(source, ocr="llamaparse", tier=tier, parser_version="latest",
                            cache_dir=tmp_path / "cache", use_cache=False)
    assert parsed.page_count == 1 and "1024" in parsed.pages[0].text
    assert parsed.parser.tier == llamaparse.normalize_tier(tier)

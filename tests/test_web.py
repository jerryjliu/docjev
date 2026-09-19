"""Offline tests for the demo's library boundary and local asset isolation."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from pypdf import PdfWriter

from jev_docs.errors import ProviderError
from jev_docs.schemas import (
    ClassificationResult,
    Page,
    ParsedDocument,
    ParserInfo,
    RunMetrics,
    Segment,
    SplitResult,
)
from jev_docs.web import app as web

RULES = {"categories": [{"id": "invoice", "description": "A payment request."}]}


def test_safe_child_accepts_aliased_root_but_rejects_escape(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(actual, target_is_directory=True)
    segment = actual / "segment.pdf"
    segment.write_bytes(b"%PDF segment")
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF outside")
    (actual / "escape.pdf").symlink_to(outside)

    assert web._safe_child(alias, "segment.pdf") == segment.resolve()
    assert web._safe_child(alias, "../outside.pdf") is None
    assert web._safe_child(alias, "escape.pdf") is None


@pytest.fixture
def setup_demo(tmp_path, monkeypatch):
    examples = tmp_path / "examples"
    examples.mkdir()
    source = examples / "packet.pdf"
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=200, height=250)
    writer.write(source)
    manifest = {
        "classify": [{"id": "invoice", "path": "examples/packet.pdf", "title": "Invoice", "category": "SECRET_LABEL"}],
        "split": [{"id": "packet", "path": "examples/packet.pdf", "title": "Claim packet", "segments": [{"category": "SECRET_LABEL"}]}],
    }
    (examples / "demo-manifest.json").write_text(json.dumps(manifest))
    doc = ParsedDocument(
        source_name="packet.pdf", source_sha256="source", canonical_path=str(source),
        canonical_sha256="canonical", page_count=3,
        pages=[Page(number=i, text=f"Invoice on page {i}") for i in range(1, 4)],
        parser=ParserInfo(name="liteparse", version="fixture"),
        metrics=RunMetrics(conversion_ms=2, ocr_ms=30, total_ms=32),
    )
    calls = []

    def parse(path, **kwargs):
        calls.append((Path(path), kwargs))
        kwargs["progress"]("ocr")
        return doc

    def previews(_canonical, directory):
        directory.mkdir(parents=True)
        paths = []
        for index in range(3):
            path = directory / f"page-{index}.jpg"
            path.write_bytes(b"fixture image")
            paths.append(path)
        return paths

    monkeypatch.setattr(web, "parse_document", parse)
    monkeypatch.setattr(web, "render_preview", previews)
    app = web.create_app(tmp_path, tmp_path / "runs")
    return app, doc, calls


async def finish(client, run_id):
    for _ in range(100):
        response = await client.get(f"/api/runs/{run_id}")
        data = response.json()
        if data["status"] in {"complete", "error"}:
            return data
        await asyncio.sleep(0.01)
    pytest.fail("The background job did not finish")


@pytest.mark.asyncio
async def test_classification_uses_shared_library_and_opaque_assets(setup_demo, monkeypatch):
    app, document, calls = setup_demo
    seen = []

    async def classify(doc, rules, **kwargs):
        seen.append((doc, rules, kwargs))
        return ClassificationResult(
            category="invoice", category_probability=0.92, probabilities={"invoice": 0.92, "other": 0.08},
            document=doc.public_info(), engine="jev", model="fixture",
            metrics=RunMetrics(conversion_ms=2, ocr_ms=30, decision_ms=10, total_ms=42),
        )

    monkeypatch.setattr(web, "classify_document", classify)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        response = await client.post("/api/runs", data={"task": "classify", "rules": json.dumps(RULES), "sample_id": "invoice"})
        assert response.status_code == 202
        result = await finish(client, response.json()["id"])
        assert result["status"] == "complete"
        assert result["result"]["category"] == "invoice"
        assert result["result"]["metrics"]["decision_ms"] == 10
        assert seen[0][0] is document
        assert seen[0][1].categories[0].description == "A payment request."
        assert seen[0][2] == {"engine": "jev", "model": None}
        assert calls[0][1]["ocr"] == "liteparse"
        assert [page["number"] for page in result["preview"]["pages"]] == [1, 2, 3]
        pdf_url = result["preview"]["pdf"]
        assert str(document.canonical_path) not in json.dumps(result)
        assert (await client.get(pdf_url)).content.startswith(b"%PDF")
        download = next(item for item in result["downloads"] if item["kind"] == "json")
        assert (await client.get(download["url"])).json()["category"] == "invoice"
        assert (await client.get(f"/api/runs/{result['id']}/assets/no-such-token")).status_code == 404
        assert (await client.get("/api/runs/unknown")).status_code == 404


@pytest.mark.asyncio
async def test_split_exports_follow_manifest_ids_not_filename_sort(setup_demo, monkeypatch):
    app, _, _ = setup_demo

    async def split(doc, rules, **kwargs):
        return SplitResult(
            segments=[Segment(id="first", category="invoice", pages=[1, 2]),
                      Segment(id="second", category="invoice", pages=[3])],
            document=doc.public_info(), engine="jev", model="fixture", metrics=RunMetrics(total_ms=14),
        )

    def export(doc, result, directory):
        directory.mkdir()
        manifest = []
        for segment, filename in zip(result.segments, ["z-first.pdf", "a-second.pdf"], strict=True):
            (directory / filename).write_bytes(b"%PDF segment")
            manifest.append({"id": segment.id, "file": filename})
        return {"segments": manifest}

    monkeypatch.setattr(web, "split_document", split)
    monkeypatch.setattr(web, "export_segments", export)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        response = await client.post("/api/runs", data={"task": "split", "rules": json.dumps(RULES), "sample_id": "packet"})
        result = await finish(client, response.json()["id"])
        assert result["status"] == "complete"
        assert [s["pages"] for s in result["result"]["segments"]] == [[1, 2], [3]]
        downloads = [item for item in result["downloads"] if item["kind"] == "pdf"]
        assert [(item["segment_id"], item["name"]) for item in downloads] == [("first", "z-first.pdf"), ("second", "a-second.pdf")]


@pytest.mark.asyncio
async def test_local_origin_guard_and_private_samples(setup_demo, monkeypatch):
    app, _, calls = setup_demo
    monkeypatch.setenv("TYPESAFE_API_KEY", "DO_NOT_EXPOSE_THIS_VALUE")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        sample_response = await client.get("/api/samples")
        assert "SECRET_LABEL" not in sample_response.text
        assert "DO_NOT_EXPOSE" not in sample_response.text
        assert sample_response.json()["providers"]["jev"] is True
        assert all("path" not in item for item in sample_response.json()["samples"])
        hostile = await client.post("/api/runs", headers={"Origin": "https://example.com"}, data={})
        assert hostile.status_code == 403
        assert (await client.get("/", headers={"Host": "attacker.example"})).status_code == 403
        assert (await client.post("/api/runs", headers={"Origin": "http://localhost"}, data={})).status_code == 422
        assert not calls


@pytest.mark.asyncio
async def test_reject_bad_input_before_provider_call(setup_demo):
    app, _, calls = setup_demo
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        fields = {"task": "classify", "rules": json.dumps(RULES), "sample_id": "invoice"}
        assert (await client.post("/api/runs", data={**fields, "rules": '{"categories": []}'})).status_code == 422
        assert (await client.post("/api/runs", data={**fields, "sample_id": "../../etc/passwd"})).status_code == 404
        assert (await client.post("/api/runs", data={**fields, "task": "split"})).status_code == 404
        fields.pop("sample_id")
        assert (await client.post("/api/runs", data=fields, files={"file": ("x.exe", b"exe")})).status_code == 422
        assert (await client.post("/api/runs", data=fields, files={"file": ("x.pdf", b"")})).status_code == 422
        assert not calls


@pytest.mark.asyncio
async def test_unexpected_errors_do_not_leak_provider_secrets(setup_demo, monkeypatch):
    app, _, _ = setup_demo

    async def fail(*args, **kwargs):
        raise RuntimeError("Authorization: Bearer SECRET_CREDENTIAL")

    monkeypatch.setattr(web, "classify_document", fail)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        response = await client.post("/api/runs", data={"task": "classify", "rules": json.dumps(RULES), "sample_id": "invoice"})
        run = await finish(client, response.json()["id"])
        assert run["status"] == "error"
        assert "SECRET_CREDENTIAL" not in json.dumps(run)
        assert "doctor" in run["error"]
        assert run["result"] is None


@pytest.mark.asyncio
async def test_actionable_library_errors_and_static_assets(setup_demo, monkeypatch):
    app, _, _ = setup_demo

    async def fail(*args, **kwargs):
        raise ProviderError("Set TYPESAFE_API_KEY to run Jev.")

    monkeypatch.setattr(web, "classify_document", fail)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        response = await client.post("/api/runs", data={"task": "classify", "rules": json.dumps(RULES), "sample_id": "invoice"})
        run = await finish(client, response.json()["id"])
        assert run["error"] == "Set TYPESAFE_API_KEY to run Jev."
        assert (await client.get("/")).status_code == 200
        assert (await client.get("/static/app.js")).status_code == 200
        assert (await client.get("/static/assets/brand/fonts/OverusedGrotesk-Regular.ttf")).status_code == 200
        assert (await client.get("/static/assets/brand/fonts/OverusedGrotesk-LICENSE.txt")).status_code == 200


@pytest.mark.asyncio
async def test_saved_comparison_is_optional_and_sanitized(setup_demo, tmp_path):
    app, _, _ = setup_demo
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        assert (await client.get("/api/comparison")).json() == {"available": False, "groups": []}
        results = tmp_path / "benchmarks" / "results"
        results.mkdir(parents=True)
        summary = {"groups": [{"task": "classify", "engine": "jev", "model": "fixture",
                               "scope": "decision_only", "concurrency": 1,
                               "decision_p50_ms": 100, "accuracy": 0.8,
                               "internal_path": "/private/path", "api_key": "SECRET"}]}
        (results / "latest-summary.json").write_text(json.dumps(summary))
        response = await client.get("/api/comparison")
        assert response.json()["available"] is True
        assert response.json()["groups"][0]["accuracy"] == 0.8
        assert "SECRET" not in response.text
        assert "/private" not in response.text


@pytest.mark.asyncio
async def test_real_demo_is_default_with_original_source_links(setup_demo, tmp_path, monkeypatch):
    monkeypatch.delenv("JEV_DOCS_DEMO_SET", raising=False)
    real = tmp_path / "examples" / "real"
    for task in ("classify", "split"):
        (real / task).mkdir(parents=True)
        (real / task / "rules.yaml").write_text(json.dumps({
            "categories": [{"id": "tax_form", "description": "An official tax form."}]
        }))
    (real / "demo-manifest.json").write_text(json.dumps({
        "classify": [{"id": "official-form", "path": "examples/packet.pdf", "title": "Official form",
                      "category": "HIDDEN_EXPECTED_LABEL", "source_url": "https://www.irs.gov/pub/irs-pdf/fw9.pdf",
                      "source_title": "IRS Form W-9", "sources": [{"url": "javascript:alert(1)", "title": "Unsafe"}]}],
        "split": [{"id": "official-packet", "path": "examples/packet.pdf", "title": "Forms packet",
                   "provenance_kind": "assembled", "source_note": "Original pages combined in one PDF.",
                   "sources": [{"url": "https://www.irs.gov/pub/irs-pdf/fw9.pdf", "title": "IRS W-9"}]}],
    }))
    app = web.create_app(tmp_path, tmp_path / "real-runs")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        response = await client.get("/api/samples")
        data = response.json()
        assert data["demo_set"] == {"id": "real", "label": "Original public documents"}
        assert [sample["id"] for sample in data["samples"]] == ["official-form", "official-packet"]
        assert data["rules"]["classify"]["categories"][0]["id"] == "tax_form"
        assert data["samples"][0]["provenance"]["sources"] == [{"url": "https://www.irs.gov/pub/irs-pdf/fw9.pdf", "title": "IRS Form W-9"}]
        assert data["samples"][1]["provenance"]["kind"] == "assembled"
        assert "HIDDEN_EXPECTED_LABEL" not in response.text
        assert (await client.get("/api/samples/official-form/pdf")).content.startswith(b"%PDF")
        results = tmp_path / "benchmarks" / "results"
        results.mkdir(parents=True)
        (results / "latest-summary.json").write_text(json.dumps({"groups": [{"task": "classify", "accuracy": 1}]}))
        assert (await client.get("/api/comparison")).json()["available"] is False
    monkeypatch.setenv("JEV_DOCS_DEMO_SET", "synthetic")
    synthetic = web.create_app(tmp_path, tmp_path / "synthetic-runs")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=synthetic), base_url="http://localhost") as client:
        data = (await client.get("/api/samples")).json()
        assert data["demo_set"] == {"id": "synthetic", "label": "Synthetic test fixtures"}
        assert data["samples"][0]["id"] == "invoice"
        assert data["samples"][0]["provenance"]["kind"] == "synthetic"


def test_explicit_real_set_does_not_silently_load_synthetic(tmp_path, monkeypatch):
    monkeypatch.setenv("JEV_DOCS_DEMO_SET", "real")
    with pytest.raises(ValueError, match="real demo set is missing"):
        web.create_app(tmp_path, tmp_path / "runs")


class FakeRaceEngine:
    def __init__(self, name, model):
        self.name = name
        self.model = model
        self.closed = False

    async def aclose(self):
        self.closed = True


@pytest.fixture
def race_engines(monkeypatch):
    prepared = []

    def make(engine, model):
        service = FakeRaceEngine(engine, model)
        prepared.append(service)
        return service

    monkeypatch.setattr(web, "make_race_engine", make)
    return prepared


async def prepare_race(client, task="classify", sample="invoice"):
    response = await client.post("/api/race/prepare", json={"task": task, "sample_id": sample})
    assert response.status_code == 202
    preparation_id = response.json()["id"]
    for _ in range(100):
        data = (await client.get(f"/api/race/preparations/{preparation_id}")).json()
        if data["status"] in {"ready", "error"}:
            return data
        await asyncio.sleep(0.005)
    pytest.fail("Shared OCR did not finish")


async def finish_race(client, race_id):
    for _ in range(100):
        data = (await client.get(f"/api/race/runs/{race_id}")).json()
        if data["status"] == "complete":
            return data
        await asyncio.sleep(0.005)
    pytest.fail("Model comparison did not finish")


def race_classification(doc, engine):
    return ClassificationResult(
        category="invoice", document=doc.public_info(), engine=engine.name, model=engine.model,
        metrics=RunMetrics(decision_ms=12 if engine.name == "jev" else 29, total_ms=15),
    )


@pytest.mark.asyncio
async def test_race_prepares_once_then_runs_concurrently_on_identical_isolated_inputs(setup_demo, monkeypatch, race_engines):
    app, original, parse_calls = setup_demo
    seen = {}
    both_entered = asyncio.Event()
    allow_jev, allow_openai = asyncio.Event(), asyncio.Event()

    async def classify(doc, rules, *, engine, model):
        assert len(race_engines) == 2  # Both clients existed before either timed operation.
        assert engine in race_engines  # Library receives instances, never cold string factories.
        seen[engine.name] = (doc.model_dump(), rules.model_dump(), doc, rules)
        # Mutation by one adapter cannot affect the other or the prepared source.
        doc.pages[0].text = f"MUTATED BY {engine.name}"
        rules.categories[0].description = f"MUTATED BY {engine.name}"
        if len(seen) == 2:
            both_entered.set()
        await (allow_jev if engine.name == "jev" else allow_openai).wait()
        return race_classification(doc, engine)

    monkeypatch.setattr(web, "classify_document", classify)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        preparation = await prepare_race(client)
        assert preparation["status"] == "ready"
        assert preparation["can_start"] is True
        assert preparation["ocr_metrics"]["ocr_ms"] == 30
        assert len(parse_calls) == 1
        assert parse_calls[0][1]["use_cache"] is False
        assert not seen  # Preparation makes no model calls.
        response = await client.post("/api/race/start", json={"preparation_id": preparation["id"], "rules": RULES})
        assert response.status_code == 202
        race_id = response.json()["id"]
        await asyncio.wait_for(both_entered.wait(), timeout=1)
        partial = (await client.get(f"/api/race/runs/{race_id}")).json()
        assert {e["status"] for e in partial["engines"].values()} == {"running"}
        allow_jev.set()
        for _ in range(100):
            partial = (await client.get(f"/api/race/runs/{race_id}")).json()
            if partial["engines"]["jev"]["status"] == "complete":
                break
            await asyncio.sleep(0.005)
        assert partial["engines"]["jev"]["result"]["metrics"]["decision_ms"] == 12
        assert partial["engines"]["openai"]["status"] == "running"
        allow_openai.set()
        result = await finish_race(client, race_id)
        assert [e["status"] for e in result["engines"].values()] == ["complete", "complete"]
        assert all(service.closed for service in race_engines)
        assert seen["jev"][0] == seen["openai"][0]
        assert seen["jev"][1] == seen["openai"][1]
        assert seen["jev"][2] is not seen["openai"][2] and seen["jev"][2] is not original
        assert seen["jev"][0]["metrics"] == RunMetrics().model_dump()
        assert original.metrics.ocr_ms == 30 and original.pages[0].text == "Invoice on page 1"
        assert result["ocr_text_sha256"] == preparation["ocr_text_sha256"]
        assert len(result["rules_sha256"]) == 64
        assert len(parse_calls) == 1
        assert (await client.post("/api/race/start", json={"preparation_id": preparation["id"], "rules": RULES})).status_code == 409
        prepared_state = (await client.get(f"/api/race/preparations/{preparation['id']}")).json()
        assert prepared_state["can_start"] is False
        payload = (await client.get(result["download"])).json()
        assert payload["comparison"]["engines"]["openai"]["result"]["metrics"]["decision_ms"] == 29
        assert payload["preparation"]["ocr_metrics"]["total_ms"] == 32
        assert str(original.canonical_path) not in json.dumps(payload)


@pytest.mark.asyncio
async def test_race_engine_failure_does_not_cancel_success_or_leak_errors(setup_demo, monkeypatch, race_engines):
    app, _, _ = setup_demo
    reached = []

    async def classify(doc, rules, *, engine, model):
        reached.append(engine.name)
        if engine.name == "openai":
            raise RuntimeError("Authorization: SECRET /Users/private/document.pdf")
        await asyncio.sleep(0)
        return race_classification(doc, engine)

    monkeypatch.setattr(web, "classify_document", classify)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        prep = await prepare_race(client)
        response = await client.post("/api/race/start", json={"preparation_id": prep["id"], "rules": RULES})
        result = await finish_race(client, response.json()["id"])
        assert sorted(reached) == ["jev", "openai"]
        assert result["engines"]["jev"]["status"] == "complete"
        assert result["engines"]["openai"]["status"] == "error"
        assert result["engines"]["openai"]["result"] is None
        assert "SECRET" not in json.dumps(result) and "/Users/" not in json.dumps(result)
        assert all(service.closed for service in race_engines)


@pytest.mark.asyncio
async def test_race_client_setup_failure_is_independent_and_redacted(setup_demo, monkeypatch):
    app, _, _ = setup_demo
    service = FakeRaceEngine("jev", "jev-1.13.0")

    def make(name, model):
        if name == "openai":
            raise RuntimeError("SECRET_CREDENTIAL")
        return service

    async def classify(doc, rules, *, engine, model):
        assert engine is service
        return race_classification(doc, engine)

    monkeypatch.setattr(web, "make_race_engine", make)
    monkeypatch.setattr(web, "classify_document", classify)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        prep = await prepare_race(client)
        assert prep["status"] == "ready"
        response = await client.post("/api/race/start", json={"preparation_id": prep["id"], "rules": RULES})
        result = await finish_race(client, response.json()["id"])
        assert result["engines"]["jev"]["status"] == "complete"
        assert result["engines"]["openai"]["status"] == "error"
        assert "SECRET" not in json.dumps(result)
        assert service.closed


@pytest.mark.asyncio
async def test_race_split_results_cover_same_pages_without_export_timing(setup_demo, monkeypatch, race_engines):
    app, original, _ = setup_demo
    seen = []

    async def split(doc, rules, *, engine, model):
        seen.append((engine.name, [p.text for p in doc.pages], doc.metrics.model_dump()))
        return SplitResult(
            segments=[Segment(id="first", category="invoice", pages=[1, 2]), Segment(id="second", category="invoice", pages=[3])],
            document=doc.public_info(), engine=engine.name, model=model,
            metrics=RunMetrics(decision_ms=23, total_ms=24),
        )

    def unexpected_export(*args):
        pytest.fail("Race decision times must not include PDF export")

    monkeypatch.setattr(web, "split_document", split)
    monkeypatch.setattr(web, "export_segments", unexpected_export)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        prep = await prepare_race(client, task="split", sample="packet")
        response = await client.post("/api/race/start", json={"preparation_id": prep["id"], "rules": RULES})
        result = await finish_race(client, response.json()["id"])
        assert len(seen) == 2 and seen[0][1:] == seen[1][1:]
        assert seen[0][1] == [p.text for p in original.pages]
        assert result["task"] == "split"
        assert [s["pages"] for s in result["engines"]["jev"]["result"]["segments"]] == [[1, 2], [3]]
        assert result["engines"]["openai"]["result"]["metrics"]["export_ms"] == 0


@pytest.mark.asyncio
async def test_race_reuses_local_origin_guards_and_opaque_assets(setup_demo, race_engines):
    app, original, parse_calls = setup_demo
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        assert (await client.get("/race")).status_code == 200
        assert (await client.get("/static/race.css")).status_code == 200
        for endpoint in ["/api/race/prepare", "/api/race/start"]:
            response = await client.post(endpoint, headers={"Origin": "https://attacker.example"}, json={})
            assert response.status_code == 403
        assert (await client.get("/race", headers={"Host": "attacker.example"})).status_code == 403
        assert not parse_calls
        assert (await client.post("/api/race/prepare", json={"task": "classify", "sample_id": "../../etc/passwd"})).status_code == 404
        assert (await client.post("/api/race/prepare", json={"task": "split", "sample_id": "invoice"})).status_code == 404
        assert (await client.post("/api/race/start", json={"preparation_id": "unknown", "rules": RULES})).status_code == 404
        prep = await prepare_race(client)
        assert str(original.canonical_path) not in json.dumps(prep)
        assert "SECRET_LABEL" not in json.dumps(prep)
        assert (await client.get(prep["preview"]["pdf"])).content.startswith(b"%PDF")
        assert (await client.get(f"/api/race/preparations/{prep['id']}/assets/unknown")).status_code == 404
        assert (await client.post("/api/race/start", json={"preparation_id": prep["id"], "rules": {"categories": []}})).status_code == 422
        assert (await client.get("/api/race/runs/unknown")).status_code == 404


def test_race_jev_uses_one_attempt_like_baseline(monkeypatch):
    from jev_docs import engines

    service = FakeRaceEngine("jev", "fixture")
    service.max_retries = 1
    monkeypatch.setattr(engines, "make_engine", lambda *args: service)
    assert web.make_race_engine("jev", "fixture") is service
    assert service.max_retries == 0


@pytest.mark.asyncio
async def test_race_preserves_failed_request_evidence(setup_demo, monkeypatch, race_engines):
    from jev_docs.schemas import RequestRecord

    app, _, _ = setup_demo

    async def classify(doc, rules, *, engine, model):
        if engine.name == "openai":
            raise ProviderError("OpenAI request failed (503).", requests=[RequestRecord(
                provider="openai", model=model, task="classify", status="error",
                elapsed_ms=41, cost_status="unknown", error_code="503",
            )])
        return race_classification(doc, engine)

    monkeypatch.setattr(web, "classify_document", classify)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        prep = await prepare_race(client)
        response = await client.post("/api/race/start", json={"preparation_id": prep["id"], "rules": RULES})
        race = await finish_race(client, response.json()["id"])
        records = race["engines"]["openai"]["requests"]
        assert len(records) == 1 and records[0]["elapsed_ms"] == 41
        assert records[0]["cost_status"] == "unknown" and records[0]["cost_usd"] is None
        assert race["engines"]["jev"]["max_retries"] == race["engines"]["openai"]["max_retries"] == 0


@pytest.mark.asyncio
async def test_race_closes_prepared_unused_clients_at_shutdown(setup_demo, race_engines):
    app, _, _ = setup_demo
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
            prep = await prepare_race(client)
            assert prep["can_start"] is True
            assert not any(service.closed for service in race_engines)
    assert len(race_engines) == 2 and all(service.closed for service in race_engines)

"""A small local UI over the public library; no separate inference implementation."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import secrets
import tempfile
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from jev_docs.errors import JevDocsError
from jev_docs.schemas import Model, ParsedDocument, RequestRecord, RuleSet, RunMetrics

STATIC = Path(__file__).with_name("static")
MAX_UPLOAD_BYTES = 30 * 1024 * 1024
ALLOWED_SUFFIXES = {".pdf", ".docx", ".pptx"}
logger = logging.getLogger(__name__)


def parse_document(*args: Any, **kwargs: Any) -> Any:
    from jev_docs.documents import parse_document as parse

    return parse(*args, **kwargs)


async def classify_document(*args: Any, **kwargs: Any) -> Any:
    from jev_docs.classify import aclassify_document

    return await aclassify_document(*args, **kwargs)


async def split_document(*args: Any, **kwargs: Any) -> Any:
    from jev_docs.split import asplit_document

    return await asplit_document(*args, **kwargs)


def export_segments(*args: Any, **kwargs: Any) -> Any:
    from jev_docs.export import export_segments as export

    return export(*args, **kwargs)


@dataclass
class Run:
    id: str
    task: str
    directory: Path
    name: str
    status: str = "queued"
    stage: str = "Waiting to start"
    document: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    assets: dict[str, Path] = field(default_factory=dict)
    preview: dict[str, Any] | None = None
    downloads: list[dict[str, Any]] = field(default_factory=list)
    started: float = field(default_factory=time.perf_counter)
    elapsed_ms: float = 0

    def add_asset(self, path: Path) -> str:
        token = secrets.token_urlsafe(18)
        self.assets[token] = path.resolve()
        return f"/api/runs/{self.id}/assets/{token}"

    def public(self) -> dict[str, Any]:
        elapsed = self.elapsed_ms if self.status in {"complete", "error"} else (time.perf_counter() - self.started) * 1000
        return {
            "id": self.id, "task": self.task, "name": self.name, "status": self.status,
            "stage": self.stage, "elapsed_ms": elapsed, "document": self.document,
            "result": self.result, "error": self.error, "preview": self.preview,
            "downloads": self.downloads,
        }



RACE_MODELS = {"jev": "jev-1.13.0", "openai": "gpt-5.6-luna"}


def make_race_engine(engine: str, model: str) -> Any:
    from jev_docs.engines import make_engine

    service = make_engine(engine, model)
    if engine == "jev":
        # A single live comparison uses one attempt for either provider.
        service.max_retries = 0
    return service


class RacePrepareRequest(Model):
    task: Literal["classify", "split"]
    sample_id: str
    use_cache: bool = False


class RaceStartRequest(Model):
    preparation_id: str
    rules: RuleSet


@dataclass
class RacePreparation:
    id: str
    task: str
    title: str
    directory: Path
    provenance: dict[str, Any]
    status: str = "preparing"
    stage: str = "Reading with LiteParse"
    document: ParsedDocument | None = None
    preview: dict[str, Any] | None = None
    error: str | None = None
    assets: dict[str, Path] = field(default_factory=dict)
    ocr_text_sha256: str | None = None
    services: dict[str, Any] = field(default_factory=dict)
    service_errors: dict[str, str] = field(default_factory=dict)
    consumed: bool = False

    def add_asset(self, path: Path) -> str:
        token = secrets.token_urlsafe(18)
        self.assets[token] = path.resolve()
        return f"/api/race/preparations/{self.id}/assets/{token}"

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id, "task": self.task, "title": self.title,
            "status": self.status, "stage": self.stage, "error": self.error,
            "can_start": self.status == "ready" and not self.consumed,
            "document": self.document.public_info() if self.document else None,
            "ocr_metrics": self.document.metrics.model_dump(mode="json") if self.document else None,
            "ocr_text_sha256": self.ocr_text_sha256, "preview": self.preview,
            "provenance": self.provenance,
        }


@dataclass
class RaceRun:
    id: str
    preparation_id: str
    task: str
    rules_sha256: str
    ocr_text_sha256: str
    status: str = "running"
    engines: dict[str, dict[str, Any]] = field(default_factory=dict)
    started: float = field(default_factory=time.perf_counter)
    elapsed_ms: float = 0
    download: str | None = None

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id, "preparation_id": self.preparation_id, "task": self.task,
            "status": self.status, "engines": self.engines,
            "rules_sha256": self.rules_sha256, "ocr_text_sha256": self.ocr_text_sha256,
            "scope": "One live run; same OCR text and rules; decision times exclude OCR and export.",
            "elapsed_ms": self.elapsed_ms if self.status == "complete" else (time.perf_counter() - self.started) * 1000,
            "download": self.download,
        }


def _content_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _project_root(project_dir: str | Path | None) -> Path:
    if project_dir:
        return Path(project_dir).resolve()
    configured = os.environ.get("JEV_DOCS_PROJECT_DIR")
    if configured:
        return Path(configured).resolve()
    cwd = Path.cwd().resolve()
    if any((cwd / path).is_file() for path in ("examples/real/demo-manifest.json", "examples/demo-manifest.json")):
        return cwd
    # The parent package may bundle examples for installed-wheel use.
    packaged = Path(__file__).resolve().parents[1]
    if any((packaged / path).is_file() for path in ("examples/real/demo-manifest.json", "examples/demo-manifest.json")):
        return packaged
    return cwd


def _safe_child(root: Path, value: str) -> Path | None:
    root = root.resolve()
    candidate = (root / value).resolve()
    if candidate.is_relative_to(root) and candidate.is_file():
        return candidate
    return None


def _demo_set(root: Path) -> tuple[str, Path]:
    """Prefer authentic public documents, with an explicit synthetic fixture override."""
    real_manifest = root / "examples" / "real" / "demo-manifest.json"
    selected = os.environ.get("JEV_DOCS_DEMO_SET", "real" if real_manifest.is_file() else "synthetic")
    if selected not in {"real", "synthetic"}:
        raise ValueError("JEV_DOCS_DEMO_SET must be real or synthetic.")
    manifest = real_manifest if selected == "real" else root / "examples" / "demo-manifest.json"
    if selected == "real" and not manifest.is_file():
        raise ValueError("The real demo set is missing examples/real/demo-manifest.json.")
    return selected, manifest


def _source_links(item: dict[str, Any]) -> list[dict[str, str]]:
    candidates = item.get("sources", [])
    if item.get("source_url"):
        candidates = [{"url": item["source_url"], "title": item.get("source_title", "Original source")}, *candidates]
    links: list[dict[str, str]] = []
    for source in candidates:
        if not isinstance(source, dict):
            continue
        url = str(source.get("url", source.get("source_url", "")))
        try:
            parsed = urlsplit(url)
            valid = parsed.scheme == "https" and bool(parsed.hostname)
        except ValueError:
            valid = False
        if valid and not any(link["url"] == url for link in links):
            links.append({"url": url, "title": str(source.get("title", source.get("name", "Original source")))})
    return links


def _samples(root: Path, manifest: Path, demo_set: str) -> dict[str, dict[str, Any]]:
    if not manifest.is_file():
        return {}
    raw = json.loads(manifest.read_text())
    found = {}
    for task in ("classify", "split"):
        for item in raw.get(task, []):
            path = _safe_child(root, item["path"])
            if path is None or path.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            sample_id = str(item["id"])
            if sample_id in found:
                raise ValueError("Demo sample IDs must be unique")
            found[sample_id] = {
                "id": sample_id, "task": task, "title": item.get("title", path.stem),
                "filename": path.name, "format": path.suffix[1:].upper(), "path": path,
                "provenance": {
                    "kind": item.get("provenance_kind", ("assembled" if task == "split" else "original") if demo_set == "real" else "synthetic"),
                    "issuer": str(item.get("issuer", "")),
                    "note": item.get("source_note", ""),
                    "sources": _source_links(item),
                },
            }
    return found


def _rules(root: Path, task: str, demo_set: str) -> dict[str, Any]:
    examples = root / "examples" / "real" if demo_set == "real" else root / "examples"
    path = examples / task / "rules.yaml"
    if path.is_file():
        from jev_docs.rules import load_rules

        return load_rules(path).model_dump()
    if demo_set == "real":
        raise ValueError(f"The real demo set requires examples/real/{task}/rules.yaml.")
    defaults = {
        "classify": [("invoice", "A request for payment with line items, an amount due, and payment terms."),
                     ("purchase_order", "A buyer's authorization to purchase goods or services."),
                     ("contract", "An agreement describing obligations and terms between parties."),
                     ("resume", "A candidate's employment history, education, and skills."),
                     ("pitch_deck", "Presentation introducing a business, its market, and investment proposition.")],
        "split": [("claim_form", "A completed insurance claim form with claim details."),
                  ("incident_report", "A factual account of an incident, its location, and circumstances."),
                  ("repair_estimate", "Proposed repairs and their estimated costs before work is authorized."),
                  ("invoice", "A request for payment for goods or services already delivered."),
                  ("correspondence", "Letters or messages discussing the claim or supporting documents.")],
    }
    return RuleSet.model_validate({"categories": [{"id": key, "description": value} for key, value in defaults[task]]}).model_dump()


def render_preview(canonical: Path, directory: Path) -> list[Path]:
    """Render actual canonical pages for previews; keep displayed page numbers exact."""
    import pypdfium2 as pdfium

    directory.mkdir(parents=True, exist_ok=True)
    pages = []
    with pdfium.PdfDocument(canonical) as pdf:
        for index in range(len(pdf)):
            page = pdf[index]
            bitmap = page.render(scale=min(1.4, 1250 / max(page.get_size())))
            try:
                target = directory / f"page-{index + 1:04d}.jpg"
                bitmap.to_pil().convert("RGB").save(target, quality=88)
                pages.append(target)
            finally:
                bitmap.close()
                page.close()
    return pages


def create_app(project_dir: str | Path | None = None, run_dir: str | Path | None = None) -> FastAPI:
    """Create the local demo, using a checkout or installed bundled examples.

    Override project_dir or JEV_DOCS_PROJECT_DIR to point at another example collection.
    All downloads are opaque asset tokens registered by a run; client paths are never read.
    """
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await close_unused_clients()

    app = FastAPI(title="DocJev", docs_url=None, redoc_url=None, lifespan=lifespan)
    root = _project_root(project_dir)
    workspace = (Path(run_dir) if run_dir else Path(tempfile.mkdtemp(prefix="jev-docs-demo-"))).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    demo_set, manifest = _demo_set(root)
    samples = _samples(root, manifest, demo_set)
    runs: dict[str, Run] = {}
    tasks: set[asyncio.Task[Any]] = set()
    semaphore = asyncio.Semaphore(1)
    app.state.runs = runs
    app.state.background_tasks = tasks

    @app.middleware("http")
    async def local_requests(request: Request, call_next: Any) -> Any:
        host = request.url.hostname or ""
        if host not in {"localhost", "127.0.0.1", "::1", "testserver"}:
            return JSONResponse({"detail": "This demo serves localhost only."}, status_code=403)
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
            source = urlsplit(origin)
            if source.scheme != request.url.scheme or source.netloc != request.url.netloc:
                return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
        return response

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/samples")
    def list_samples() -> dict[str, Any]:
        return {
            "samples": [{k: v for k, v in item.items() if k != "path"} for item in samples.values()],
            "rules": {task: _rules(root, task, demo_set) for task in ("classify", "split")},
            "demo_set": {"id": demo_set, "label": "Original public documents" if demo_set == "real" else "Synthetic test fixtures"},
            "providers": {"jev": bool(os.environ.get("TYPESAFE_API_KEY")),
                          "openai": bool(os.environ.get("OPENAI_API_KEY")),
                          "llamaparse": bool(os.environ.get("LLAMA_CLOUD_API_KEY"))},
        }

    @app.get("/api/samples/{sample_id}/pdf")
    def sample_pdf(sample_id: str) -> FileResponse:
        sample = samples.get(sample_id)
        if sample is None or sample["path"].suffix.lower() != ".pdf":
            raise HTTPException(404, "PDF preview is available after reading this document.")
        return FileResponse(sample["path"], media_type="application/pdf")

    @app.get("/api/comparison")
    def saved_comparison() -> dict[str, Any]:
        """Expose only published aggregate measurements, never benchmark prompts or labels."""
        results_dir = root / "benchmarks" / "results"
        preferred = results_dir / "latest-summary.json"
        candidates = [preferred] if preferred.is_file() else sorted(
            results_dir.glob("*/summary.json"), key=lambda path: path.stat().st_mtime, reverse=True
        )
        if not candidates:
            return {"available": False, "groups": []}
        try:
            summary = json.loads(candidates[0].read_text())
        except (ValueError, OSError):
            return {"available": False, "groups": []}
        # The old synthetic evaluation must never look like evidence about new real inputs.
        benchmark_set = summary.get("demo_set", "synthetic")
        if benchmark_set != demo_set:
            return {"available": False, "groups": []}
        public_fields = {
            "task", "engine", "model", "scope", "concurrency", "planned_unique",
            "completed_unique", "completion_rate", "decision_p50_ms", "decision_p95_ms",
            "latency_samples", "accuracy", "packet_exact_match", "decision_cost_usd_known",
            "unknown_cost_calls",
        }
        groups = [{key: value for key, value in group.items() if key in public_fields}
                  for group in summary.get("groups", []) if isinstance(group, dict)]
        return {"available": bool(groups), "label": "Saved measured evaluation", "demo_set": benchmark_set,
                "dataset_label": "Real-document evaluation" if benchmark_set == "real" else "Synthetic evaluation", "groups": groups}

    async def execute(run: Run, source: Path, rules: RuleSet, ocr: str, tier: str,
                      engine: str, model: str | None, use_cache: bool) -> None:
        async with semaphore:
            try:
                run.status, run.stage = "parsing", "Converting and reading document"
                loop = asyncio.get_running_loop()

                def update_stage(stage: str) -> None:
                    stages = {"converting": "Preparing canonical PDF pages", "ocr": "Reading document content",
                              "ocr_cached": "Loading previously read pages"}
                    run.stage = stages.get(stage, "Reading document content")

                def progress(stage: str) -> None:
                    loop.call_soon_threadsafe(update_stage, stage)

                document = await asyncio.to_thread(parse_document, source, ocr=ocr, tier=tier,
                                                    cache_dir=workspace / "ocr-cache", use_cache=use_cache,
                                                    progress=progress)
                run.document = document.public_info()
                canonical = Path(document.canonical_path)
                images = await asyncio.to_thread(render_preview, canonical, run.directory / "pages")
                run.preview = {"pdf": run.add_asset(canonical), "pages": [
                    {"number": index + 1, "image": run.add_asset(path)} for index, path in enumerate(images)
                ]}
                run.status = "deciding"
                run.stage = "Classifying with Jev" if run.task == "classify" else "Finding categories and document boundaries"
                if engine != "jev":
                    run.stage = "Classifying with the LLM" if run.task == "classify" else "Splitting with the LLM"
                operation = classify_document if run.task == "classify" else split_document
                result = await operation(document, rules, engine=engine, model=model)
                run.result = result.model_dump(mode="json")
                if run.task == "split":
                    run.stage = "Exporting document segments"
                    manifest = await asyncio.to_thread(export_segments, document, result, run.directory / "segments")
                    for segment in manifest["segments"]:
                        pdf = _safe_child(run.directory / "segments", segment["file"])
                        if pdf is None:
                            raise RuntimeError("Exported segment is missing")
                        run.downloads.append({"name": pdf.name, "kind": "pdf",
                                              "segment_id": segment["id"], "url": run.add_asset(pdf)})
                    # Export may update the shared metrics.
                    run.result = result.model_dump(mode="json")
                json_path = run.directory / "result.json"
                json_path.write_text(json.dumps(run.result, indent=2) + "\n")
                run.downloads.append({"name": f"{run.task}-result.json", "kind": "json", "url": run.add_asset(json_path)})
                run.status, run.stage = "complete", "Complete"
            except JevDocsError as exc:
                run.error = str(exc)
                run.status, run.stage = "error", "Run could not finish"
            except Exception as exc:
                # Provider bodies / local paths can contain secrets. Only typed user-facing errors
                # are returned, and arbitrary exception messages are never logged to the browser.
                logger.warning("Demo run failed with %s", type(exc).__name__)
                run.error = "The run could not finish. Check the local setup with docjev doctor and try again."
                run.status, run.stage = "error", "Run could not finish"
            finally:
                run.elapsed_ms = (time.perf_counter() - run.started) * 1000

    @app.post("/api/runs", status_code=202)
    async def start_run(
        task: str = Form(...), rules: str = Form(...), sample_id: str | None = Form(None),
        file: Annotated[UploadFile | None, File()] = None, ocr: str = Form("liteparse"),
        tier: str = Form("agentic"), engine: str = Form("jev"), model: str | None = Form(None),
        use_cache: bool = Form(True),
    ) -> dict[str, Any]:
        if task not in {"classify", "split"} or ocr not in {"liteparse", "llamaparse"}:
            raise HTTPException(422, "Choose a valid task and OCR provider.")
        if tier not in {"cost_effective", "agentic", "agentic_plus"} or engine not in {"jev", "openai"}:
            raise HTTPException(422, "Choose a valid parsing tier and decision engine.")
        if bool(sample_id) == bool(file):
            raise HTTPException(422, "Choose one sample or upload one document.")
        if sum(run.status not in {"complete", "error"} for run in runs.values()) >= 8:
            raise HTTPException(429, "The local queue is full. Wait for a run to finish.")
        try:
            parsed_rules = RuleSet.model_validate_json(rules)
        except ValidationError as exc:
            messages = [str(item["msg"]) for item in exc.errors(include_input=False)]
            raise HTTPException(422, "Invalid rules: " + "; ".join(messages)) from exc
        sample = samples.get(sample_id or "")
        if sample_id and (sample is None or sample["task"] != task):
            raise HTTPException(404, "Sample not found for this task.")
        run_id = secrets.token_urlsafe(18)
        directory = workspace / run_id
        directory.mkdir()
        if file:
            name = Path((file.filename or "document").replace("\\", "/")).name
            if Path(name).suffix.lower() not in ALLOWED_SUFFIXES:
                raise HTTPException(422, "Please use a PDF, DOCX, or PPTX document.")
            source = directory / name
            size = 0
            try:
                with source.open("wb") as stream:
                    while chunk := await file.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_UPLOAD_BYTES:
                            raise HTTPException(413, "Please choose a document smaller than 30 MB.")
                        stream.write(chunk)
            except HTTPException:
                source.unlink(missing_ok=True)
                raise
            finally:
                await file.close()
            if not size:
                source.unlink(missing_ok=True)
                raise HTTPException(422, "The uploaded document is empty.")
        else:
            assert sample is not None
            source, name = sample["path"], sample["filename"]
        run = Run(id=run_id, task=task, directory=directory, name=name)
        runs[run_id] = run
        background = asyncio.create_task(execute(run, source, parsed_rules, ocr, tier, engine, model or None, use_cache))
        tasks.add(background)
        background.add_done_callback(tasks.discard)
        return run.public()

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        if run_id not in runs:
            raise HTTPException(404, "Run not found.")
        return runs[run_id].public()

    @app.get("/api/runs/{run_id}/assets/{token}")
    def get_asset(run_id: str, token: str, download: bool = False) -> FileResponse:
        run = runs.get(run_id)
        path = run.assets.get(token) if run else None
        if path is None or not path.is_file():
            raise HTTPException(404, "Asset not found.")
        return FileResponse(path, filename=path.name if download else None)

    # The comparison view prepares one immutable input, then starts two independent
    # decision coroutines. It does not enqueue two end-to-end /api/runs jobs.
    preparations: dict[str, RacePreparation] = {}
    races: dict[str, RaceRun] = {}
    app.state.race_preparations = preparations
    app.state.race_runs = races

    def background_job(coroutine: Any) -> None:
        job = asyncio.create_task(coroutine)
        tasks.add(job)
        job.add_done_callback(tasks.discard)

    async def close_unused_clients() -> None:
        services = [service for preparation in preparations.values() for service in preparation.services.values()]
        if services:
            await asyncio.gather(*(service.aclose() for service in services), return_exceptions=True)
        for preparation in preparations.values():
            preparation.services.clear()

    @app.get("/race")
    def race_view() -> FileResponse:
        return FileResponse(STATIC / "race.html")

    async def prepare_race(preparation: RacePreparation, source: Path, use_cache: bool) -> None:
        async with semaphore:
            try:
                loop = asyncio.get_running_loop()

                def update_stage(stage: str) -> None:
                    preparation.stage = {"converting": "Preparing PDF pages", "ocr": "Reading with LiteParse",
                                         "ocr_cached": "Loading cached OCR"}.get(stage, "Reading with LiteParse")

                def progress(stage: str) -> None:
                    loop.call_soon_threadsafe(update_stage, stage)

                document = await asyncio.to_thread(
                    parse_document, source, ocr="liteparse", tier="agentic",
                    cache_dir=workspace / "ocr-cache", use_cache=use_cache, progress=progress,
                )
                # Keep original OCR telemetry separate from both decision-only copies.
                preparation.document = document.model_copy(deep=True)
                preparation.ocr_text_sha256 = _content_hash([page.model_dump() for page in document.pages])
                preparation.stage = "Preparing source previews"
                canonical = Path(document.canonical_path)
                images = await asyncio.to_thread(render_preview, canonical, preparation.directory / "pages")
                preparation.preview = {"pdf": preparation.add_asset(canonical), "pages": [
                    {"number": index + 1, "image": preparation.add_asset(path)}
                    for index, path in enumerate(images)
                ]}
                preparation.stage = "Preparing model clients"

                async def prepare_client(engine: str, model: str) -> None:
                    try:
                        # No inference occurs here. Cold imports and SDK construction
                        # finish before either model's recorded decision interval starts.
                        preparation.services[engine] = await asyncio.to_thread(make_race_engine, engine, model)
                    except Exception as exc:
                        logger.warning("Comparison %s setup failed with %s", engine, type(exc).__name__)
                        preparation.service_errors[engine] = str(exc) if isinstance(exc, JevDocsError) else "This model is unavailable. Check the local setup with docjev doctor."

                await asyncio.gather(*(prepare_client(engine, model) for engine, model in RACE_MODELS.items()))
                preparation.status, preparation.stage = "ready", "OCR ready"
            except Exception as exc:
                logger.warning("Comparison preparation failed with %s", type(exc).__name__)
                preparation.error = str(exc) if isinstance(exc, JevDocsError) else "The document could not be prepared. Check the local setup with docjev doctor."
                preparation.status, preparation.stage = "error", "Preparation failed"

    @app.post("/api/race/prepare", status_code=202)
    async def prepare_comparison(request: RacePrepareRequest) -> dict[str, Any]:
        sample = samples.get(request.sample_id)
        if sample is None or sample["task"] != request.task:
            raise HTTPException(404, "Sample not found for this task.")
        if sum(item.status == "preparing" for item in preparations.values()) >= 4:
            raise HTTPException(429, "Wait for the current OCR preparation to finish.")
        preparation_id = secrets.token_urlsafe(18)
        directory = workspace / f"race-{preparation_id}"
        directory.mkdir()
        preparation = RacePreparation(preparation_id, request.task, sample["title"], directory, sample["provenance"])
        preparations[preparation_id] = preparation
        background_job(prepare_race(preparation, sample["path"], request.use_cache))
        return preparation.public()

    @app.get("/api/race/preparations/{preparation_id}")
    def get_preparation(preparation_id: str) -> dict[str, Any]:
        preparation = preparations.get(preparation_id)
        if preparation is None:
            raise HTTPException(404, "Prepared document not found.")
        return preparation.public()

    @app.get("/api/race/preparations/{preparation_id}/assets/{token}")
    def get_preparation_asset(preparation_id: str, token: str, download: bool = False) -> FileResponse:
        preparation = preparations.get(preparation_id)
        path = preparation.assets.get(token) if preparation else None
        if path is None or not path.is_file():
            raise HTTPException(404, "Asset not found.")
        return FileResponse(path, filename=path.name if download else None)

    async def execute_race(race: RaceRun, preparation: RacePreparation, rules: RuleSet,
                           services: dict[str, Any]) -> None:
        prepared_document = preparation.document
        assert prepared_document is not None
        operation = classify_document if preparation.task == "classify" else split_document

        async def execute_engine(engine: str, model: str) -> None:
            state = race.engines[engine]
            # Copies protect exact initial text/rules against either adapter mutating them.
            document = prepared_document.model_copy(deep=True)
            document.metrics = RunMetrics()
            engine_rules = rules.model_copy(deep=True)
            service = services.get(engine)
            if service is None:
                state["status"] = "error"
                state["error"] = preparation.service_errors.get(engine, "This model is unavailable.")
                return
            state["status"] = "running"
            started = time.perf_counter()
            state["started_offset_ms"] = (started - race.started) * 1000
            try:
                result = await operation(document, engine_rules, engine=service, model=model)
                state["result"] = result.model_dump(mode="json")
                state["status"] = "complete"
            except Exception as exc:
                logger.warning("Comparison %s failed with %s", engine, type(exc).__name__)
                state["status"] = "error"
                state["error"] = str(exc) if isinstance(exc, JevDocsError) else "This model could not finish. Check the local setup with docjev doctor."
                if isinstance(exc, JevDocsError):
                    state["requests"] = [record.model_dump(mode="json") for record in exc.requests
                                         if isinstance(record, RequestRecord)]
            finally:
                state["elapsed_ms"] = (time.perf_counter() - started) * 1000
                try:
                    await service.aclose()
                except Exception as exc:
                    logger.warning("Comparison %s cleanup failed with %s", engine, type(exc).__name__)

        # Both coroutines are scheduled together and have independent error handling.
        await asyncio.gather(*(execute_engine(engine, model) for engine, model in RACE_MODELS.items()))
        race.elapsed_ms = (time.perf_counter() - race.started) * 1000
        race.status = "complete"
        result_path = preparation.directory / f"comparison-{race.id}.json"
        result_path.write_text(json.dumps({"preparation": preparation.public(), "comparison": race.public()}, indent=2) + "\n")
        race.download = preparation.add_asset(result_path)

    @app.post("/api/race/start", status_code=202)
    async def start_comparison(request: RaceStartRequest) -> dict[str, Any]:
        preparation = preparations.get(request.preparation_id)
        if preparation is None:
            raise HTTPException(404, "Prepared document not found.")
        if preparation.status != "ready" or preparation.document is None:
            raise HTTPException(409, "Wait until OCR is ready before running both models.")
        if preparation.consumed:
            raise HTTPException(409, "Prepare another run before starting the models again.")
        if any(race.status == "running" for race in races.values()):
            raise HTTPException(409, "A comparison is already running. Wait for both models to finish.")
        race = RaceRun(
            id=secrets.token_urlsafe(18), preparation_id=preparation.id, task=preparation.task,
            rules_sha256=_content_hash(request.rules.model_dump()),
            ocr_text_sha256=preparation.ocr_text_sha256 or "",
            engines={engine: {"engine": engine, "model": model, "status": "queued", "result": None,
                              "error": None, "elapsed_ms": None, "started_offset_ms": None,
                              "max_retries": 0, "requests": []}
                     for engine, model in RACE_MODELS.items()},
        )
        races[race.id] = race
        services = preparation.services
        preparation.services = {}
        preparation.consumed = True
        background_job(execute_race(race, preparation, request.rules, services))
        return race.public()

    @app.get("/api/race/runs/{race_id}")
    def get_comparison(race_id: str) -> dict[str, Any]:
        race = races.get(race_id)
        if race is None:
            raise HTTPException(404, "Comparison not found.")
        return race.public()

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app

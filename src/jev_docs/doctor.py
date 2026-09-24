"""Safe installation diagnostics: credential presence, never credential values."""

from __future__ import annotations

import importlib.metadata
import os
import platform
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .conversion import converter_version, find_soffice


def doctor(*, smoke: bool = False) -> dict[str, Any]:
    packages: dict[str, str | None] = {}
    for package in ("docjev", "liteparse", "typesafe-sdk", "llama-cloud", "openai",
                    "httpx", "pypdf", "pypdfium2", "Pillow", "fastapi"):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    office = find_soffice()
    office_version = None
    if office:
        try:
            office_version = converter_version(office)
        except Exception:
            office_version = "could not start"
    diagnostics: dict[str, Any] = {
        "python": platform.python_version(), "platform": platform.system(), "packages": packages,
        "credentials": {name: bool(os.environ.get(name)) for name in
                        ("TYPESAFE_API_KEY", "LLAMA_CLOUD_API_KEY", "OPENAI_API_KEY",
                         "OPENROUTER_API_KEY")},
        "tools": {"libreoffice": {"available": bool(office), "version": office_version},
                  "fontconfig": {"available": bool(shutil.which("fc-list"))}},
        "formats": {"pdf": bool(packages["liteparse"]), "docx": bool(office), "pptx": bool(office)},
        "local_ocr": {"status": "not_exercised", "note": "Use doctor --smoke to test scanned OCR. Initial OCR may download English language data."},
        "cloud_authentication": "not_tested",
    }
    if smoke:
        diagnostics["local_ocr"] = _smoke()
    return diagnostics


def _smoke() -> dict[str, Any]:
    """Generate a raster-only PDF with Pillow; this detects missing OCR language data."""
    from PIL import Image, ImageDraw, ImageFont

    from .documents import parse_document

    with tempfile.TemporaryDirectory(prefix="jev-docs-doctor-") as directory:
        root = Path(directory)
        image = Image.new("RGB", (1600, 1000), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=60)
        draw.text((100, 120), "INVOICE 1024", font=font, fill="black")
        draw.text((100, 240), "Total due 250 dollars", font=font, fill="black")
        image.save(root / "scan.pdf", resolution=150)
        image.close()
        try:
            parsed = parse_document(root / "scan.pdf", cache_dir=root / "cache", use_cache=False)
            passed = "1024" in parsed.pages[0].text and "250" in parsed.pages[0].text
            return {"status": "passed" if passed else "failed", "tested": "raster-only-pdf",
                    "page_count": parsed.page_count, "ocr_ms": parsed.metrics.ocr_ms,
                    "expected_numbers_found": passed}
        except Exception as exc:
            return {"status": "failed", "error_type": type(exc).__name__,
                    "note": "Local scanned OCR was not successful; check installation and language-data availability."}


check_environment = doctor

"""Retained PDF pagination and isolated LibreOffice conversion."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from pypdf import PdfReader

from .cache import atomic_write, cache_key, digest_file
from .errors import DocumentError

SUPPORTED_SUFFIXES = frozenset({".pdf", ".docx", ".pptx"})
_RENDER_LOCK = threading.Lock()  # PDFium calls must not run concurrently in-process.


@dataclass
class CanonicalDocument:
    path: Path
    sha256: str
    page_count: int
    conversion: dict[str, Any]


def find_soffice() -> str | None:
    for name in ("soffice", "libreoffice"):
        executable = shutil.which(name)
        if executable:
            return executable
    mac = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    return str(mac) if mac.is_file() else None


def converter_version(executable: str) -> str:
    try:
        result = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=15, check=True
        )
        return result.stdout.strip().splitlines()[0]
    except (OSError, subprocess.SubprocessError, IndexError) as exc:
        raise DocumentError("LibreOffice could not start. Check the installation with docjev doctor.") from exc


def font_fingerprint() -> dict[str, str]:
    """Fingerprint installed font names/styles; no home-directory paths are retained."""
    executable = shutil.which("fc-list")
    if not executable:
        return {"font_inventory": "unavailable", "font_policy": "system fonts; substitution possible"}
    try:
        result = subprocess.run(
            [executable, "--format", "%{family}|%{style}\\n"],
            capture_output=True, text=True, timeout=15, check=True,
        )
        names = "\n".join(sorted(set(result.stdout.splitlines())))
        return {"font_inventory_sha256": hashlib.sha256(names.encode()).hexdigest(),
                "font_policy": "system fonts; substitution possible"}
    except (OSError, subprocess.SubprocessError):
        return {"font_inventory": "unavailable", "font_policy": "system fonts; substitution possible"}


def bundled_font_directory() -> Path | None:
    directory = Path(__file__).parent / "web" / "static" / "assets" / "brand" / "fonts"
    return directory if directory.is_dir() else None


def font_environment(scratch: Path) -> dict[str, str]:
    """Expose bundled brand fonts only to this converter process and its children."""
    environment = os.environ.copy()
    fonts = bundled_font_directory()
    if not fonts:
        return environment
    config = scratch / "fonts.conf"
    system_configs = [Path("/etc/fonts/fonts.conf"), Path("/opt/homebrew/etc/fonts/fonts.conf")]
    includes = "".join(f'<include ignore_missing="yes">{escape(str(path))}</include>'
                       for path in system_configs if path.is_file())
    config.write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig>'
                      f'{includes}<dir>{escape(str(fonts.resolve()))}</dir>'
                      f'<cachedir>{escape(str(scratch / "font-cache"))}</cachedir></fontconfig>')
    environment["FONTCONFIG_FILE"] = str(config)
    environment["SAL_FONTPATH"] = str(fonts.resolve())
    return environment


def pdf_page_count(path: Path) -> int:
    try:
        reader = PdfReader(path, strict=False)
        if reader.is_encrypted:
            raise DocumentError("Encrypted PDFs are not supported. Supply a decrypted PDF.")
        count = len(reader.pages)
        if count < 1:
            raise DocumentError("The PDF has no pages.")
        return count
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError("The PDF could not be read. Check that it is a valid, unencrypted PDF.") from exc


def canonicalize(path: Path, root: Path, *, use_cache: bool = True) -> CanonicalDocument:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise DocumentError("Unsupported document format. Supported formats: PDF, DOCX, PPTX.")
    source_hash = digest_file(path)
    if suffix == ".pdf":
        count = pdf_page_count(path)
        target = root / "canonical" / f"{source_hash}.pdf"
        if not target.is_file() or digest_file(target) != source_hash:
            atomic_write(target, path.read_bytes())
        return CanonicalDocument(target, source_hash, count,
                                 {"kind": "original-pdf", "page_numbering": "one-based-original"})

    executable = find_soffice()
    if not executable:
        raise DocumentError("DOCX and PPTX require LibreOffice. Install it and run docjev doctor.")
    export_filter = "writer_pdf_Export" if suffix == ".docx" else "impress_pdf_Export"
    settings = {"kind": "libreoffice", "version": converter_version(executable),
                "source_format": suffix[1:], "export_filter": export_filter,
                "profile": "isolated-temporary", "hidden_slides": "included",
                "page_numbering": "one-based-rendered-pdf", **font_fingerprint()}
    fonts = bundled_font_directory()
    if fonts:
        settings["bundled_fonts_sha256"] = cache_key({font.name: digest_file(font)
                                                     for font in sorted(fonts.glob("*.ttf"))})
        settings["font_profile"] = "task-local-fontconfig-and-sal-fontpath-v1"
    key = cache_key({"source": source_hash, "conversion": settings, "schema": 1})
    metadata_path = root / "conversions" / f"{key}.json"
    if use_cache and metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text())
            target = root / "canonical" / f"{metadata['canonical_sha256']}.pdf"
            if digest_file(target) == metadata["canonical_sha256"]:
                return CanonicalDocument(target, metadata["canonical_sha256"],
                                         pdf_page_count(target), settings)
        except (OSError, ValueError, KeyError):
            pass

    with tempfile.TemporaryDirectory(prefix="jev-docs-convert-") as directory:
        scratch = Path(directory)
        original = scratch / f"source{suffix}"
        shutil.copyfile(path, original)
        profile = scratch / "profile"
        profile.mkdir()
        # Office inputs cannot reuse a running user's profile or execute macros.
        (profile / "user").mkdir()
        (profile / "user" / "registrymodifications.xcu").write_text(
            '<?xml version="1.0"?><oor:items xmlns:oor="http://openoffice.org/2001/registry">'
            '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
            '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>'
            '</item></oor:items>'
        )
        output = scratch / "output"
        output.mkdir()
        options = {"ExportHiddenSlides": {"type": "boolean", "value": "true"}}
        filter_arg = f"pdf:{export_filter}:{json.dumps(options, separators=(',', ':'))}"
        try:
            converted = subprocess.run(
                [executable, f"-env:UserInstallation={profile.as_uri()}", "--headless",
                 "--nologo", "--nodefault", "--norestore", "--convert-to", filter_arg,
                 "--outdir", str(output), str(original)],
                capture_output=True, timeout=180, check=False, env=font_environment(scratch),
            )
        except subprocess.TimeoutExpired as exc:
            raise DocumentError("Office conversion exceeded 180 seconds. Export this file to PDF manually.") from exc
        except OSError as exc:
            raise DocumentError("LibreOffice could not launch for document conversion.") from exc
        rendered = output / "source.pdf"
        if converted.returncode or not rendered.is_file():
            raise DocumentError("LibreOffice could not convert this document. Check that it opens correctly, or export it to PDF manually.")
        count = pdf_page_count(rendered)
        if suffix == ".pptx":
            try:
                with zipfile.ZipFile(original) as archive:
                    slides = [name for name in archive.namelist()
                              if name.startswith("ppt/slides/slide") and name.endswith(".xml")
                              and "/" not in name.removeprefix("ppt/slides/")]
                if count != len(slides):
                    raise DocumentError("PowerPoint conversion did not produce one PDF page per slide.")
            except zipfile.BadZipFile as exc:
                raise DocumentError("The PPTX is not a valid Office document.") from exc
        canonical_hash = digest_file(rendered)
        # Content-hash paths stay immutable even if a later fresh Office render
        # changes a PDF timestamp or font substitution. Old results remain usable.
        target = root / "canonical" / f"{canonical_hash}.pdf"
        atomic_write(target, rendered.read_bytes())
        atomic_write(metadata_path, json.dumps({"canonical_sha256": canonical_hash}).encode())
        return CanonicalDocument(target, canonical_hash, count, settings)


def render_page_image(path: str | Path, page_number: int, *, scale: float = 1.5) -> Any:
    """Render one 1-based canonical PDF page; callers own the returned PIL image."""
    import pypdfium2 as pdfium

    with _RENDER_LOCK:
        document = pdfium.PdfDocument(str(path))
        try:
            if not 1 <= page_number <= len(document):
                raise DocumentError("Requested preview page is outside the document.")
            page = document[page_number - 1]
            try:
                bitmap = page.render(scale=scale)
                try:
                    return bitmap.to_pil().convert("RGB").copy()
                finally:
                    bitmap.close()
            finally:
                page.close()
        finally:
            document.close()


def render_page_png(path: str | Path, page_number: int, output: str | Path, *, scale: float = 1.5) -> Path:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image = render_page_image(path, page_number, scale=scale)
    try:
        image.save(destination, format="PNG")
    finally:
        image.close()
    return destination


def is_visually_blank(path: Path, page_number: int) -> bool:
    """Only nearly white, mark-free rendered pages qualify; scans with noise do not."""
    try:
        image = render_page_image(path, page_number, scale=2.0)
        try:
            low, _ = image.convert("L").getextrema()
            return bool(low >= 250)
        finally:
            image.close()
    except Exception as exc:
        raise DocumentError(f"Could not verify whether page {page_number} is blank.") from exc

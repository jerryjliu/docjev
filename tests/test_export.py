import hashlib

import pytest
from pypdf import PdfReader, PdfWriter

from jev_docs.errors import DocumentError
from jev_docs.export import export_segments
from jev_docs.schemas import RunMetrics, Segment, SplitResult


def test_export_real_page_membership(tmp_path, document):
    source = tmp_path / "source.pdf"
    writer = PdfWriter()
    for width in [100, 200, 300, 400]:
        writer.add_blank_page(width=width, height=500)
    writer.write(source)
    document.canonical_path = str(source)
    document.canonical_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    result = SplitResult(
        segments=[
            Segment(id="segment-001", category="invoice", pages=[1, 2]),
            Segment(id="segment-002", category="invoice", pages=[3, 4]),
        ],
        document=document.public_info(),
        engine="fixture",
        model="fixture",
        metrics=RunMetrics(),
    )
    manifest = export_segments(document, result, tmp_path / "exports")
    pages = PdfReader(tmp_path / "exports" / manifest["segments"][1]["file"]).pages
    assert [p.mediabox.width for p in pages] == [300, 400]
    with pytest.raises(DocumentError):
        export_segments(document, result, tmp_path / "exports")


def export_fixture(tmp_path, document):
    source = tmp_path / "source.pdf"
    writer = PdfWriter()
    for _ in range(document.page_count):
        writer.add_blank_page(width=100, height=500)
    writer.write(source)
    document.canonical_path = str(source)
    document.canonical_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    result = SplitResult(
        segments=[Segment(id="segment-001", category="invoice", pages=[1, 2, 3, 4])],
        document=document.public_info(), engine="fixture", model="fixture", metrics=RunMetrics(),
    )
    return source, result


@pytest.mark.parametrize("identifier", ["../outside", "/tmp/outside", "folder/file", "a\\b"])
def test_export_rejects_path_segments_before_creating_output(tmp_path, document, identifier):
    _, result = export_fixture(tmp_path, document)
    result.segments[0].id = identifier
    destination = tmp_path / "exports"
    with pytest.raises(DocumentError, match="Segment IDs"):
        export_segments(document, result, destination)
    assert not destination.exists()


def test_export_rejects_changed_pdf_with_same_page_count(tmp_path, document):
    source, result = export_fixture(tmp_path, document)
    changed = PdfWriter()
    for _ in range(document.page_count):
        changed.add_blank_page(width=300, height=500)
    changed.write(source)
    destination = tmp_path / "exports"
    with pytest.raises(DocumentError, match="does not match"):
        export_segments(document, result, destination)
    assert not destination.exists()


def test_export_rejects_duplicate_ids_and_mutated_coverage(tmp_path, document):
    _, result = export_fixture(tmp_path, document)
    result.segments = [
        Segment(id="segment-001", category="invoice", pages=[1, 2]),
        Segment(id="segment-001", category="invoice", pages=[3, 4]),
    ]
    with pytest.raises(DocumentError, match="unique"):
        export_segments(document, result, tmp_path / "exports")
    result.segments[1].id = "segment-002"
    result.segments[1].pages = [4]
    with pytest.raises(DocumentError, match="exactly once"):
        export_segments(document, result, tmp_path / "exports")
    assert not (tmp_path / "exports").exists()


@pytest.mark.parametrize("filename", ["segment-001-invoice.pdf", "manifest.json"])
def test_overwrite_does_not_follow_output_symlinks(tmp_path, document, filename):
    _, result = export_fixture(tmp_path, document)
    target = tmp_path / "outside"
    target.write_bytes(b"keep this")
    destination = tmp_path / "exports"
    destination.mkdir()
    (destination / filename).symlink_to(target)
    with pytest.raises(DocumentError, match="symbolic link"):
        export_segments(document, result, destination, overwrite=True)
    assert target.read_bytes() == b"keep this"


def test_overwrite_replaces_existing_regular_files(tmp_path, document):
    _, result = export_fixture(tmp_path, document)
    destination = tmp_path / "exports"
    export_segments(document, result, destination)
    (destination / "segment-001-invoice.pdf").write_bytes(b"stale")
    export_segments(document, result, destination, overwrite=True)
    assert len(PdfReader(destination / "segment-001-invoice.pdf").pages) == 4
    assert not list(destination.glob(".jev-docs-*"))


def test_export_rejects_mutated_empty_segment(tmp_path, document):
    _, result = export_fixture(tmp_path, document)
    empty = Segment(id="segment-empty", category="invoice", pages=[1])
    empty.pages = []
    result.segments.insert(0, empty)
    with pytest.raises(DocumentError, match="nonempty"):
        export_segments(document, result, tmp_path / "exports")
    assert not (tmp_path / "exports").exists()

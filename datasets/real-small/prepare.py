"""Offline assembly and strict, read-only verification for the real-small v1 corpus.

`verify_corpus(root)` takes the repository root. It never downloads, repairs,
relabels, or refreezes data. Assembly/freeze are explicit pre-inference operations.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from collections import Counter
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter

VERSION = "real-small-v1"
PREFIX = Path("datasets/real-small/v1")
CATEGORIES = {"tax_form", "financial_report", "press_release", "legal_notice", "other"}
REPO = Path(__file__).resolve().parents[2]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> Any:
    return json.loads(path.read_text())


def write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def resolve(root: Path, name: str) -> Path:
    path = root / name
    check(
        not Path(name).is_absolute() and path.resolve().is_relative_to(root.resolve()),
        f"Non-repository path: {name}",
    )
    return path


def page_signature(page: Any) -> dict[str, Any]:
    contents = page.get_contents()
    return {
        "content_sha256": hashlib.sha256(contents.get_data() if contents else b"").hexdigest(),
        "mediabox": [float(x) for x in page.mediabox],
        "cropbox": [float(x) for x in page.cropbox],
        "rotation": page.rotation,
    }


def render_hashes(path: Path) -> list[str]:
    import pypdfium2 as pdfium

    hashes = []
    with pdfium.PdfDocument(path) as document:
        for page in document:
            try:
                bitmap = page.render(scale=1.0)
                try:
                    image = bitmap.to_pil().convert("RGB")
                    hashes.append(
                        hashlib.sha256(
                            f"{image.width}x{image.height}:RGB:".encode() + image.tobytes()
                        ).hexdigest()
                    )
                finally:
                    bitmap.close()
            finally:
                page.close()
    return hashes


def assert_same_pages(
    original: Path, packet: Path, packet_pages: list[int], *, render: bool
) -> None:
    """Compare complete source pages, including resources through raster equality."""
    src, dst = PdfReader(original), PdfReader(packet)
    check(len(src.pages) == len(packet_pages), "Missing source pages in packet mapping")
    for src_page, dst_number in zip(src.pages, packet_pages, strict=True):
        check(1 <= dst_number <= len(dst.pages), "Packet page out of range")
        check(
            page_signature(src_page) == page_signature(dst.pages[dst_number - 1]),
            f"Changed page content/geometry: {original.name} -> {packet.name}:{dst_number}",
        )
    if render:
        expected, actual = render_hashes(original), render_hashes(packet)
        check(
            expected == [actual[n - 1] for n in packet_pages],
            f"Changed rendered page/resources: {original.name} -> {packet.name}",
        )


def identity_paths(root: Path) -> list[str]:
    base = root / PREFIX
    names = {
        p.relative_to(root).as_posix()
        for p in base.rglob("*")
        if p.is_file() and p.name != "FREEZE.json"
    }
    names.add("datasets/real-small/prepare.py")
    names.add("datasets/LICENSE")
    names.update({"examples/real/SOURCE.json", "examples/real/demo-manifest.json"})
    demo = read(root / "examples/real/demo-manifest.json")
    names.update(x["path"] for x in demo["classify"] + demo["split"])
    return sorted(names)


def verify_corpus(
    root: Path | None = None, *, require_review: bool = True, render: bool = False
) -> dict[str, Any]:
    """Verify repository-local corpus; return counts or raise ValueError. No writes/network."""
    root = Path(root or REPO).resolve()
    base = root / PREFIX
    try:
        source_rows = read(base / "SOURCE.json")["sources"]
        annotation_rows = read(base / "annotations.json")["annotations"]
        plan = read(base / "packet-plan.json")["packets"]
        classes = read(base / "manifests/classify.json")
        splits = read(base / "manifests/split.json")
        check(len(source_rows) == 40, "Expected exactly 40 original sources")
        sources = {s["id"]: s for s in source_rows}
        check(
            len(sources) == 40 and set(sources) == {f"e{i:03}" for i in range(1, 41)},
            "Duplicate or unexpected source IDs",
        )
        annotations = {a["source_id"]: a for a in annotation_rows}
        check(
            len(annotation_rows) == 40 and set(annotations) == set(sources),
            "Missing/duplicate annotations",
        )
        counts = Counter(a["category"] for a in annotation_rows)
        check(
            set(counts) == CATEGORIES and set(counts.values()) == {8},
            "Expected five categories with eight originals each",
        )
        hashes = [s["sha256"] for s in source_rows]
        check(len(set(hashes)) == 40, "Duplicate original source bytes")
        old = read(root / "examples/real/SOURCE.json")["sources"]
        check(not set(hashes) & {s["sha256"] for s in old}, "Existing demo source leaked into test")
        check(
            not {s["source_url"] for s in source_rows} & {s["source_url"] for s in old},
            "Existing demo publication leaked into test",
        )
        page_total = 0
        for sid, source in sources.items():
            path = resolve(root, source["path"])
            check(path == root / PREFIX / "originals" / f"{sid}.pdf", "Non-neutral source filename")
            check(sha(path) == source["sha256"], f"Changed source: {sid}")
            check(path.stat().st_size == source["byte_count"], f"Changed byte count: {sid}")
            pages = PdfReader(path).pages
            count = len(pages)
            page_total += count
            check(
                count == source["page_count"]
                and source["source_pages"] == list(range(1, count + 1)),
                f"Incomplete source page inventory: {sid}",
            )
            check(
                [page_signature(p) for p in pages] == source["page_signatures"],
                f"Changed page inventory: {sid}",
            )
            check(
                source["complete_original"] is True and source["language"] == "en",
                f"Incomplete/non-English source: {sid}",
            )
            check(
                source["source_url"].startswith("https://")
                and bool(source["rights_basis"])
                and bool(source["rights_url"])
                and bool(source["content_review"]),
                f"Missing provenance/rights: {sid}",
            )
            check(
                bool(source["source_family_id"]) and bool(source["template_family"]),
                f"Missing family metadata: {sid}",
            )
            ann = annotations[sid]
            check(
                ann["source_sha256"] == source["sha256"] and ann["category"] in CATEGORIES,
                f"Bad annotation identity/label: {sid}",
            )
            check(
                bool(ann["purpose_evidence"])
                and ann["evidence_pages"]
                and all(1 <= n <= count for n in ann["evidence_pages"]),
                f"Missing annotation evidence: {sid}",
            )
            check(ann["human_review"] == "not_performed", "Unsupported human review claim")
            if require_review:
                review = ann["review"]
                check(
                    review["status"] == "approved"
                    and review["reviewer_type"] == "agent"
                    and review["reviewer_id"] != ann["annotator_id"]
                    and review["source_sha256"] == source["sha256"]
                    and review["category"] == ann["category"]
                    and bool(review["method"]),
                    f"Missing independent agent review: {sid}",
                )
        check(page_total <= 160, "Unique original pages exceed 160")
        all_ids = [r["id"] for r in classes + splits]
        check(len(set(all_ids)) == len(all_ids), "Manifest IDs are not globally unique")
        ctest = [r for r in classes if r["split"] == "test"]
        stest = [r for r in splits if r["split"] == "test"]
        check(
            len(classes) == 41 and len(ctest) == 40 and len(splits) == 9 and len(stest) == 8,
            "Expected 40+1 classification and 8+1 split entries",
        )
        check({r["id"] for r in ctest} == set(sources), "Classification source membership mismatch")
        for row in ctest:
            source = sources[row["id"]]
            check(
                row["source_ids"] == [source["id"]]
                and row["category"] == annotations[source["id"]]["category"],
                "Bad classification label",
            )
            for key in ("path", "sha256", "page_count", "source_family_id", "template_family"):
                check(
                    row[key] == source[key], f"Classification metadata mismatch: {row['id']}:{key}"
                )
        demo = read(root / "examples/real/demo-manifest.json")
        warmups = [r for r in classes + splits if r["split"] == "dev"]
        expected_warmups = [next(r for r in demo["classify"] if r["id"] == "r04"), demo["split"][0]]
        check(
            [r["id"] for r in warmups] == ["real-small-warmup-classify", "real-small-warmup-split"],
            "Unexpected excluded warmup identities",
        )
        for row, expected in zip(warmups, expected_warmups, strict=True):
            check(
                row["path"] == expected["path"]
                and row["sha256"] == expected["sha256"]
                and sha(resolve(root, row["path"])) == row["sha256"]
                and row["page_count"] == expected["page_count"]
                and row["source_ids"] == expected["source_ids"],
                "Warmup identity mismatch",
            )
            label = "category" if "category" in expected else "segments"
            check(row[label] == expected[label], "Warmup truth mismatch")
        check(
            len(plan) == 8 and {p["id"] for p in plan} == {f"p{i:03}" for i in range(1, 9)},
            "Expected eight packet plans",
        )
        packets = {p["id"]: p for p in stest}
        memberships, adjacent_packets, same_boundaries, sizes = [], 0, 0, []
        for packet in plan:
            sid_list = packet["source_ids"]
            check(
                len(sid_list) == 5 and len(set(sid_list)) == 5 and set(sid_list) <= set(sources),
                "Duplicate/missing packet sources",
            )
            memberships.extend(sid_list)
            row = packets[packet["id"]]
            check(row["source_ids"] == sid_list, "Packet source order mismatch")
            path = resolve(root, row["path"])
            check(
                path == root / PREFIX / "packets" / f"{packet['id']}.pdf",
                "Non-neutral packet filename",
            )
            check(sha(path) == row["sha256"], f"Changed packet: {packet['id']}")
            count = len(PdfReader(path).pages)
            sizes.append(count)
            check(
                count == row["page_count"] == packet["page_count"] and count <= 25,
                "Packet page count/cap mismatch",
            )
            expected_segments, expected_mapping, offset = [], [], 1
            for source_id in sid_list:
                source = sources[source_id]
                n = source["page_count"]
                pp = list(range(offset, offset + n))
                expected_segments.append(
                    {"category": annotations[source_id]["category"], "pages": pp}
                )
                expected_mapping.append(
                    {
                        "source_id": source_id,
                        "source_pages": list(range(1, n + 1)),
                        "packet_pages": pp,
                    }
                )
                assert_same_pages(resolve(root, source["path"]), path, pp, render=render)
                offset += n
            check(
                offset == count + 1 and row["segments"] == expected_segments,
                "Missing/reordered pages or bad split labels",
            )
            check(
                packet["source_page_mapping"] == expected_mapping
                and row["source_page_mapping"] == expected_mapping,
                "Bad packet provenance",
            )
            same = sum(
                a["category"] == b["category"]
                for a, b in zip(expected_segments, expected_segments[1:], strict=False)
            )
            same_boundaries += same
            adjacent_packets += bool(same)
        check(
            Counter(memberships) == Counter(sources.keys()),
            "Sources must appear exactly once across packets",
        )
        check(adjacent_packets >= 4, "Expected at least four same-category adjacency packets")
        for name in ("classify", "split"):
            import yaml

            rule = yaml.safe_load((base / f"rules/{name}.yaml").read_text())
            check({x["id"] for x in rule["categories"]} == CATEGORIES, "Rules taxonomy mismatch")
        frozen = base / "FREEZE.json"
        if frozen.exists():
            freeze = read(frozen)
            check(freeze["dataset_version"] == VERSION, "Wrong freeze version")
            paths = identity_paths(root)
            check(set(freeze["files"]) == set(paths), "Freeze file inventory changed")
            for name in paths:
                check(
                    sha(resolve(root, name)) == freeze["files"][name],
                    f"Frozen identity changed: {name}",
                )
            if require_review:
                check(
                    freeze["review_status"] == "independent-agent-reviewed", "Freeze review missing"
                )
        else:
            check(not require_review, "Corpus not frozen")
        return {
            "dataset_version": VERSION,
            "originals": 40,
            "classification_test_count": 40,
            "split_test_count": 8,
            "source_pages": page_total,
            "task_input_pages": page_total * 2,
            "true_segments": 40,
            "true_boundaries": 32,
            "same_category_boundaries": same_boundaries,
            "adjacent_same_category_packets": adjacent_packets,
            "packet_pages": sizes,
            "excluded_warmup_inputs": 2,
            "excluded_warmup_task_invocations": 4,
            "freeze_sha256": sha(frozen) if frozen.exists() else None,
        }
    except (KeyError, TypeError, IndexError, FileNotFoundError) as exc:
        raise ValueError(f"Malformed or missing corpus data: {exc}") from exc


def assemble(root: Path = REPO) -> None:
    """Explicitly create packets from the recorded plan, never touching originals."""
    base = root / PREFIX
    check(
        not (base / "FREEZE.json").exists(),
        "Frozen corpus cannot be reassembled; create a new version",
    )
    sources = {x["id"]: x for x in read(base / "SOURCE.json")["sources"]}
    annotations = {x["source_id"]: x for x in read(base / "annotations.json")["annotations"]}
    plan = read(base / "packet-plan.json")
    rows = []
    for p in plan["packets"]:
        writer = PdfWriter()
        segments, mapping, offset = [], [], 1
        for sid in p["source_ids"]:
            source = sources[sid]
            path = resolve(root, source["path"])
            check(sha(path) == source["sha256"], f"Changed original: {sid}")
            # append preserves resources/annotations; keep every page including covers.
            writer.append(path, import_outline=False)
            pages = list(range(offset, offset + source["page_count"]))
            segments.append({"category": annotations[sid]["category"], "pages": pages})
            mapping.append(
                {"source_id": sid, "source_pages": source["source_pages"], "packet_pages": pages}
            )
            offset += source["page_count"]
        path = base / "packets" / f"{p['id']}.pdf"
        writer.add_metadata(
            {
                "/Title": p["id"],
                "/Subject": "Constructed evaluation packet of complete unmodified original pages; not an official government publication.",
            }
        )
        writer.write(path)
        p.update(page_count=offset - 1, source_page_mapping=mapping)
        rows.append(
            {
                "id": p["id"],
                "path": path.relative_to(root).as_posix(),
                "split": "test",
                "segments": segments,
                "page_count": offset - 1,
                "source_ids": p["source_ids"],
                "source_family_ids": [sources[s]["source_family_id"] for s in p["source_ids"]],
                "template_family": "constructed-mixed-publications",
                "format": "pdf",
                "scan": False,
                "sha256": sha(path),
                "source_page_mapping": mapping,
                "provenance_kind": "assembled",
            }
        )
    demo = read(root / "examples/real/demo-manifest.json")
    warm = dict(
        demo["split"][0],
        id="real-small-warmup-split",
        split="dev",
        template_family="existing-real-demo",
        excluded_from_scoring=True,
    )
    rows.append(warm)
    write(base / "packet-plan.json", plan)
    write(base / "manifests/split.json", rows)


def freeze_corpus(root: Path = REPO) -> None:
    base = root / PREFIX
    check(
        not (base / "FREEZE.json").exists(),
        "Refusing to overwrite freeze; use a new corpus version",
    )
    summary = verify_corpus(root, require_review=False, render=True)
    for a in read(base / "annotations.json")["annotations"]:
        r = a["review"]
        check(
            r["status"] == "approved"
            and r["reviewer_id"] != a["annotator_id"]
            and r["source_sha256"] == a["source_sha256"]
            and r["category"] == a["category"],
            "Independent review required before freezing",
        )
    import pypdfium2 as pdfium

    write(
        base / "FREEZE.json",
        {
            "schema_version": 1,
            "dataset_version": VERSION,
            "frozen_on": "2026-09-19",
            "review_status": "independent-agent-reviewed",
            "human_review": "not_performed",
            "summary": summary,
            "assembly": {
                "pypdf": importlib.metadata.version("pypdf"),
                "pypdfium2": importlib.metadata.version("pypdfium2"),
                "pdfium": str(pdfium.PDFIUM_INFO),
                "render_scale": 1.0,
                "all_assembled_pages_pixel_equal": True,
            },
            "files": {name: sha(root / name) for name in identity_paths(root)},
        },
    )
    verify_corpus(root, require_review=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--assemble", action="store_true")
    mode.add_argument("--freeze", action="store_true")
    parser.add_argument(
        "--render", action="store_true", help="Compare every assembled page's pixels"
    )
    args = parser.parse_args()
    if args.assemble:
        assemble()
    elif args.freeze:
        freeze_corpus()
    print(json.dumps(verify_corpus(require_review=not args.assemble, render=args.render), indent=2))


if __name__ == "__main__":
    main()

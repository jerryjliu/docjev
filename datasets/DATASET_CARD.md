# Synthetic document decision dataset

Version **1.0.0**. Generator seed: **20260918**. Language: English. Content is first-party, fictional, and released under [CC0](LICENSE). This is a small controlled integration benchmark, not a representative production dataset.

## Contents

| Task | Development | Held out | Total pages | Formats |
|---|---:|---:|---:|---|
| Classification | 12 documents | 48 documents | 84 | 54 PDF, 6 DOCX |
| Splitting | 6 packets | 18 packets | 242 | PDF |

Classification has ten documents per label: `invoice`, `purchase_order`, `contract`, `resume`, `pitch_deck`, and `other`. Every class has two development and eight held-out documents, one DOCX, two image-only scans, and native PDFs. The pitch presentation in the demo also exercises PPTX. The quantified classification corpus does not include native PPTX; do not claim a PPTX accuracy estimate from it.

Splitting has six labels: `claim_form`, `incident_report`, `repair_estimate`, `invoice`, `correspondence`, and `other`. Packets contain 9-12 pages. Every packet includes two adjacent, distinct invoice sources. Their continuation pages omit the first-page title, while preserving a source reference. Six packets contain a deliberately blank page labeled `other`; five packets contain rasterized scans. Eight packets also contain unrelated material. All pages, including blanks, remain in the coverage denominator.

The separate examples contain six classification sources (PDF, scanned PDF, DOCX, and PPTX) and one nine-page claim packet. Their labels and display titles live in `examples/demo-manifest.json`. The semantically equivalent PDF/DOCX/PPTX group under `examples/fixtures/` reuses the demo deck's content and is explicitly excluded from accuracy estimates.

## Ground truth and separation

Labels follow human-authored source templates and packet assembly records. No model created or adjudicated ground truth. A new source document always creates a boundary, even when its category matches its neighbor. The manifest uses original one-based PDF pages and expected rendered Office pages. Office pagination is verified separately during conversion.

Every classification document has a unique source identity. Every packet owns disjoint constituent source identities; no source is reused across packets or across development, held-out, and demo sets. Development layouts use a top accent or left accent. Held-out PDF layouts use inset typography, a tinted masthead, an underlined masthead, or a right accent. Native Word sources use a separate held-out layout. The source prose deliberately shares a small set of semantic templates; source/template isolation does not imply broad language diversity.

Inference paths are neutral (`c001.pdf`, `s001.pdf`); source PDF metadata has the neutral title `Document`. Labels, readable demo titles, and assembly maps remain in manifests, which must never enter model prompts. Document-visible invoice references and ordinary headings are intentional task evidence. Repeated synthetic-example notices identify the data as fictional but do not identify its class.

## Reproduction and freeze

```sh
uv sync --extra datasets --extra dev
uv run python datasets/generate.py
uv run python datasets/generate.py --verify
uv run pytest tests/test_dataset_integrity.py
```

`--verify` checks source hashes, balance, coverage, source/template separation, and regenerates all PDF/DOCX documents in a temporary directory to compare exact bytes and manifests. ReportLab embeds the provided font subsets and fixes PDF timestamps; DOCX ZIP timestamps and core properties are normalized. Reproduction is defined against the repository lockfile. A different font/PDF rendering library release may change bytes.

The committed demo PPTX is an original editable source authored with Artifact Tool. `build_demo_deck.mjs` records its authoring source. Standard Python regeneration retains and hashes this source instead of requiring an additional JavaScript artifact-authoring runtime. Thus the PPTX has a **declared source hash**, not a claim of byte-identical Python regeneration. The parity fixtures are related to this deck, not new independent observations.

Freeze the JSON manifests and record their hashes in each benchmark run before testing. Changing a source or rule after observing held-out results requires a new dataset or evaluation version. No inference-derived correction is part of the generator.

## Scan and typography conditions

Scans rasterize source PDFs at 111.6 DPI, convert them to grayscale, rotate by a deterministic angle within 0.6 degrees, and apply a 0.22-pixel blur. They contain no hidden text layer. This is mild controlled degradation; the corpus does not model photographs, handwriting, heavy stains, or multilingual OCR.

The documents follow LlamaIndex colors and use Overused Grotesk with IBM Plex Mono labels. PDF fonts are embedded. Office files name the same font family; the application supplies the bundled font path during conversion. Standalone Office applications may substitute fonts unless the bundled fonts are installed. Font files retain their own licenses and are excluded from the CC0 dedication.

## Limits and suitable claims

Use this corpus to check routing, page coverage, repeated-category boundaries, source isolation, errors, and reproducible decision timing. Report accuracy with its small denominator and uncertainty. Shared phrasing and explicit document headings make some decisions easy. Packet category order is fixed, apart from inserted blank/unrelated pages, so this version does not measure arbitrary-order robustness. Performance here does not establish performance on customer records, unseen industries, long packets, mixed languages, handwriting, or adversarial documents. OCR cost/latency and decision cost/latency must be reported separately. The demo is for explanation and is excluded from held-out accuracy.

# Parser and conversion compatibility

Verified on 2026-09-18 with Python 3.12.6 on macOS. The lockfile is the reproducible dependency reference. Python 3.11 is a supported package target; its CI result is separate from these local observations.

| Component | Verified version | Checks |
|---|---|---|
| LiteParse | 2.14.6, native Python wheel | Native text; two-page raster-only scan; genuine blank page; strict page coverage |
| llama-cloud | 2.16.0 | Parse v2 upload and page Markdown retrieval for all three requested tiers |
| pypdf | 6.19.0 | Canonical PDF count, encrypted-input rejection |
| pypdfium2 | 5.13.0 | Canonical previews and conservative blank-page verification |
| LibreOffice | 26.8.0.0.alpha0 (local bundled build) | Two-page DOCX, two-slide PPTX; isolated profiles and branded-font PDF embedding |

Use a stable LibreOffice release for a production setup and verify your own output. The tested local build is an alpha; pagination can differ between converters and fonts. PDF input needs no Office software. DOCX/PPTX require a `soffice` or `libreoffice` executable (or the standard macOS LibreOffice app). `docjev doctor` reports safe dependency and credential-presence diagnostics; credential presence does not establish remote authentication.

## Page contract

All page numbers are one-based positions in a retained canonical PDF. Original PDF bytes are retained unchanged. Office files are rendered once with a fresh temporary LibreOffice profile, bounded conversion timeout, and disabled macros; PPTX conversion includes hidden slides and checks that slide count equals PDF page count. Every export and preview uses those exact retained bytes. Canonical PDFs are named by their content hash, so fresh rendering cannot overwrite an earlier result's pagination.

The converter records its version, export settings, system font-inventory fingerprint, and bundled-font content fingerprint. Bundled Overused Grotesk and IBM Plex Mono fonts are exposed through a conversion-process-only Fontconfig profile and `SAL_FONTPATH`, without installing fonts system-wide. This fixed observed Office font substitution in the local environment; fonts requested by arbitrary input documents can still be substituted when unavailable. The canonical PDF is authoritative.

OCR must return every page exactly once in source order. Missing, duplicated, reordered, failed, encrypted, and unreadable pages are errors. Empty OCR text is accepted as blank only if the corresponding PDF page renders entirely near-white (every grayscale pixel is at least 250 at 144 DPI). This conservative rule can reject noisy blank scans; visible diagrams with no readable text are errors, never inferred blanks.

## Local OCR and cache

The LiteParse Python adapter enables English local OCR and treats OCR failure as fatal. The first scanned parse may download language data; run `docjev doctor --smoke` before relying on offline execution. Local OCR has no hosted OCR API fee; machine resources still have costs. The complete Jev workflow sends normalized page text to TypeSafe.

The default local cache is `.jev-docs/cache`, excluded from Git. It contains source-derived PDF bytes and extracted text. Keys include canonical bytes, converter/font settings, parser SDK/version/tier/options, normalization, and schema version. Cached results validate their canonical hash and schema before reuse. A mutable LlamaParse `latest` selection has a 24-hour local cache lifetime. Pin a valid tier-specific version for longer reproducibility. `use_cache=False` bypasses local OCR and Office reuse and disables LlamaParse server cache; canonical PDFs still persist for export. A local hit records zero current-call OCR API cost and latency while retaining the original parser usage in `parser.options.usage` as provenance.

## Live LlamaParse contract

Calls use only `files.create(purpose="parse")` and Parse v2, with SDK retries disabled, a 180-second request timeout, and 300-second job timeout. The three user-facing tier names map to `cost_effective`, `agentic`, and `agentic_plus`. The adapter preserves Markdown headers and footers, page success flags, job ID, credits, requested version, and version resolution status. No hosted Classify/Split call or implementation is used.

Actual one-page smoke observations (native synthetic invoice; fresh server parsing, sequential calls, no inference engine):

| Tier | OCR wall time | Reported credits | Estimated USD at list rate |
|---|---:|---:|---:|
| cost-effective | 8.397 s | 3 | $0.00375 |
| agentic | 12.439 s | 10 | $0.01250 |
| agentic-plus | 12.835 s | 45 | $0.05625 |

These are smoke checks, not a comparative latency benchmark. All returned correct page identity and invoice text. Credits were reported; USD is estimated from the published $1.25/1,000-credit rate and may differ from account billing. Two earlier agentic jobs failed during result retrieval while the API contract was being diagnosed; their billed usage was unavailable and is not included in this $0.07250 successful-call total.

Two live API differences from SDK annotations matter:

- Published dates are tier-specific. The SDK's `2026-07-24` hint was rejected for cost-effective and agentic-plus; the smoke checks therefore used `latest`. The responses did not expose a resolved dated version, and the adapter explicitly records `version_resolved: false`. The CLI accepts a caller-supplied valid version; it never invents a resolved date.
- `raw_parameters` exists on the SDK response type but is not an accepted `expand` value. The adapter requests `markdown`, `usage`, and `job_metadata`. Header/footer and `success` are page fields; credits live at `job.usage.credits` and may be null. Unknown charges remain unknown.

Offline adapter tests mock the API boundary to verify contracts, errors, and usage semantics. Opt-in real checks: `JEV_DOCS_LIVE_OCR=1 uv run pytest tests/test_ocr_contract.py -m live`; this dispatches three paid one-page parses. Default tests do not use cloud credentials.

Sources: [LiteParse Python API](https://github.com/run-llama/liteparse/tree/main/packages/python), [Parse tiers and versioning](https://developers.llamaindex.ai/llamaparse/parse/guides/tiers/), [Parse pricing](https://developers.llamaindex.ai/llamaparse/general/pricing/).

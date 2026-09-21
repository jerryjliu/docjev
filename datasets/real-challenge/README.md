# Next challenge: 40 real documents, harder questions

**Status: preparation protocol only. No corpus has been selected, no human labels have been approved, and no new model calls have been made.** The published `real-small-v1` dataset and run remain immutable.

The first pilot established that the integration works on clearly labeled public-sector PDFs. The next study should test document purpose, attachment boundaries, and OCR noise without increasing the document count. It must not be presented as a representative production benchmark.

## Fixed size and spend

- **40 new complete originals**, reused once each in eight five-document packets. No generated documents, fabricated invoices, artificial scan degradation, inserted separator pages, or crops masquerading as originals.
- At most **200 unique source pages**, **25 pages per packet**, and **four documents from one template family**. Use at least ten template families. Record genuine raster scans separately from digital PDFs with a scanned signature.
- One measured pass for both engines: 40 classification + eight splitting inputs each = **96 measured task executions**, plus four excluded development warmups. A task may require multiple Jev requests; reserve for the actual request plan before running.
- **$1 estimated provider-cost ceiling**, zero retries, concurrency one, 30-second provider requests, 60-second task timeout, five-minute paid-stage ceiling. The local ceiling cannot enforce provider billing. Stop on unknown usage, a budget violation, or systemic authentication/quota failure; preserve incomplete outcomes.
- LiteParse only for this run. Shared OCR is computed locally, without a decision-provider client. Maximum ten-minute preparation stage. No VLM OCR sweep and no repeated timing sweep in this study.

## Selection matrix

| Slice | Target | What makes it useful |
|---|---:|---|
| Financial reports | 8 | Financial tables and short narrative summaries that resemble releases. |
| Press releases | 8 | Announcements containing embedded tables or attached implementation material. |
| Legal notices | 8 | Formal regulatory/procurement notices that resemble correspondence. |
| Correspondence | 8 | Complete agency letters or memos, preferably signed historical scans. |
| Other | 8 | Related instructions, guides, or factual briefs, not unrelated easy negatives. |

Across these categories, include **at least eight authentic scanned originals**, **at least eight documents a reviewer finds ambiguous between neighboring categories**, and **at least six multi-page publications with supporting attachments**. These slices may overlap. Record why each selected document qualifies; do not infer ambiguity from a model's mistake after the run.

Prefer public business-facing documents: financial disclosures, procurement decisions, regulator correspondence, and the associated announcements. Government hosting alone does not establish redistribution rights. Check actual authorship and exclusions before bundling any source. Do not publish non-public customer documents or unredacted sensitive information.

## Verified places to start sourcing

These are discovery sources, **not selected benchmark items or verified scan claims**:

- [GAO bid protest decisions](https://www.gao.gov/legal/bid-protests), including [the historical B-215242 decision](https://www.gao.gov/products/b-215242): potential original procurement decisions and archival scan candidates. Inspect complete PDFs and their rights before selection.
- [FDA letters to industry](https://www.fda.gov/medical-devices/industry-medical-devices/letters-industry): complete agency communications that can be paired with notices or announcements. Distinguish letters from third-party exhibits.
- [FDA warning letters](https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters): regulator correspondence candidates. Use the original downloadable letter when provided; do not silently convert a web article into a purported original PDF.
- [Federal Reserve 2025 releases](https://www.federalreserve.gov/newsevents/pressreleases/2025-press.htm): fresh attachment examples. At most two FOMC statement bundles; repeated issuer templates must not dominate this follow-up.

Existing v1/demo documents are excluded by SHA-256. A new date on the same template is still the same template family. Identify near duplicates and related publications explicitly.

## Label review before inference

1. Record source URL, acquisition date, original file hash, exact page count, issuer, template family, source rights, and full-document identity.
2. Propose the category, plausible alternatives, and specific page evidence. Specify whether an attachment belongs to its covering publication under the written rules. Retain a dissent field.
3. Have a **person** review every ambiguous category and attachment decision, with no model outputs shown. The reviewer may change a label or reject an item. Agent review must never be recorded as human review.
4. Resolve disagreements before freezing. A genuinely unresolved publication boundary must be excluded with a recorded reason before the run, not silently removed after scoring.
5. Construct packets from unchanged originals; retain one-based source-to-packet page maps. Include at least eight same-category boundaries across at least six packets, and both attached supporting material and genuinely separate same-category documents.
6. Verify every assembled page against its source, freeze rules/labels/hashes/order, and record a new dataset version. Do not edit `real-small-v1` or reuse its preparation receipt.

`review.csv` is a **40-slot intake worksheet**, not an annotated dataset. Every row is intentionally pending. Run `uv run python scripts/check_challenge_readiness.py` to see remaining intake blockers; the check is read-only and cannot make API calls. Passing intake is necessary but does not replace packet verification, OCR preflight, or a separately sealed execution receipt.

## Timing: two distinct views from one paid pass

Prepare each unique classification input and each packet once using a fresh, isolated local cache. Record observed conversion/OCR wall time, cache state, parser version, errors, and text hashes. Both engines then receive the identical parsed input. No extra inference calls are needed for the two views:

- **Measured decision latency:** whole-task decision wall time, with all owned Jev windows included.
- **Derived pipeline estimate:** that input's observed preparation wall time plus the engine's measured decision/validation time. Label this as a derived sum from separate stages, not directly observed end-to-end latency. Do not add a dataset-wide preparation total to a per-document median, or add medians instead of aggregating paired per-input sums.

A directly observed end-to-end timing comparison would require a separately planned measurement and cache policy. Keep it out of the headline until actually measured. Network and provider caches remain uncontrolled.

The offline preflight should confirm whether any selected packet needs more than one Jev window. If none does, explicitly state that window seams remain untested; do not add filler text or silently enlarge the corpus to force them.

## Score accuracy and the usefulness of review separately

Report classification accuracy/macro-F1/confusion matrix; page-category accuracy; boundary precision/recall/F1; exact labeled segments; exact packets; same-category boundaries; and attachment retention. Preserve full frozen denominators and show failed/skipped tasks. Break out scan, ambiguity, and attachment slices without claiming stable population estimates from tiny subgroups.

Freeze `boundary_threshold=0.5`, `min_probability=0.7`, and `boundary_review_margin=0.1` **before** fresh inference. No attachment-specific prompt or threshold tuning on held-out items. The known v1 FOMC error scores 0.76 and is not caught by the default review band; this is not a promised fix for that example.

At every non-first-page candidate boundary, compare `starts_document` with frozen truth. Evaluate `boundary_near_threshold` flags on eligible model decisions:

- Boundary-error recall: flagged wrong decisions / all wrong decisions.
- Review precision: flagged wrong decisions / all flagged decisions.
- Review workload: flagged candidate boundaries / eligible candidate boundaries; also report affected pages and segments.
- Report zero-denominator precision/recall as undefined, not 100%. Report missing boundary probabilities as unavailable, not unflagged/confident. Distinguish deterministic blank-policy boundaries from model decisions.

Report this alongside category review reasons, actual costs, request counts, p50/p95 latency, and all exceptions. No post hoc threshold sweep on the held-out set. Any later tuning needs a separate development split and another unseen evaluation.

## Remaining work before a new run

Collect and inspect the 40 originals; complete human review; verify packets; freeze the new corpus; extend the bounded runner with a separate challenge profile, review eligibility checks, and per-input preparation telemetry; pass offline preflight and the full budget reservation. **The v1 runner intentionally refuses these draft inputs.** The source collection and measured follow-up are not represented as completed by this protocol.

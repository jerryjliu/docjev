# Small real-document accuracy benchmark implementation plan

Date: September 19, 2026  
Status: Implementation phases 1–4 complete. Corpus frozen and local preparation admitted; the single scoped paid attempt is in progress.

## Overview

Implement one small, reproducible accuracy comparison of Jev and GPT-5.6 Luna using authentic documents. Reuse the existing Python benchmark harness, preserve every expected test item in the scoring denominator, and control preparation time and estimated API spend before starting inference.

The user's latest constraint is approximately 30–50 real documents, with low cost and short execution time. This plan implements the revised **40-original / 8-packet** scope in `research/2026-09-19-real-document-evaluation-options.md:16`. It retains the existing five-category taxonomy and uses LiteParse only. It does not expand the current video work.

## Fixed experiment contract

| Setting | Decision |
|---|---|
| Classification corpus | 40 complete English PDFs; 8 each of `tax_form`, `financial_report`, `press_release`, `legal_notice`, and `other` |
| Unique source-page budget | At most 160 pages across the 40 originals |
| Splitting corpus | The same 40 originals, used exactly once across 8 constructed packets of 5 originals; at most 25 pages per packet |
| Boundary challenge | At least 4 packets contain an adjacent pair of distinct originals with the same category |
| Ground truth | Original-purpose labels plus independently checked assembly boundaries; annotation method disclosed |
| Test exclusions | All 5 existing real-demo originals, revisions of those same publications, exact duplicates, and obvious near-duplicate editions |
| OCR | LiteParse; each task input prepared once and its normalized text shared by both engines |
| Engines | `jev-1.13.0` and `gpt-5.6-luna`, as in the existing real-demo configuration |
| Measured calls | 1 pass × (40 documents + 8 packets) × 2 engines = **96 task invocations** |
| Warmups | 1 existing development/demo input per task × 2 engines = **4 excluded task invocations**; no new development corpus |
| Scheduling | Concurrency 1, seeded shuffled inputs and paired engine order, reused clients |
| Retries | SDK/application retries 0; disable billable context-rejection recovery for this profile; retain deterministic local window selection |
| Spend control | **$2 local estimated guard**, including warmups and retained reservations for unknown charges |
| Time controls | 60 seconds per OCR input; 600 seconds for local preparation; 30 seconds per provider request; 60 seconds per complete decision task; 300 seconds for the paid stage including warmups |
| Reporting | Separate classification and splitting accuracy, successful-call latency, OCR preparation, warmup costs, measured costs, and incomplete/failed work |

The nominal total is **100 task invocations**, not necessarily 100 provider requests. Jev may need multiple predetermined windows for a split task. There are 40 unique source documents and 48 scored task inputs, not 48 independent sources. Original pages appear twice across the scored task inputs, for at most 320 task-input pages before warmups; this is intentional reuse.

The time limits bound local work and stop further dispatch; cancellation cannot establish whether a remote provider has stopped processing or charging. The $2 value is an estimated local admission/reservation guard, not a provider-enforced billing cap. The existing demo's price/latency observations are not a quote for this corpus.

## Current state analysis

| Existing component | Evidence and implication |
|---|---|
| Source verification and dev/test selection | `benchmarks/run.py:88` verifies file hashes. `:103` already selects development warmups, so the new manifests can reference existing demo inputs as `dev` without adding a warmup-reuse exception. |
| Reservations | `benchmarks/run.py:36` tracks reservations and retains unknown dispatched charges; `:109` uses actual parsed text when available. Keep these semantics. |
| Preflight | `benchmarks/run.py:128` computes a no-API estimate, but `:334` does not require a passing estimate before execution. CLI overrides also need full validation after application. |
| Shared OCR | `benchmarks/run.py:195` serializes and hashes prepared text and clears historical OCR metrics before decision timing. However, its native OCR call at `:208` has no deadline, and warmups at `:293` run before complete test preparation. |
| Inference | `src/jev_docs/engines/jev.py:32` and `src/jev_docs/engines/openai.py:24` already accept request timeouts. Jev's recursive context-rejection recovery at `jev.py:180` can add requests even when retries are zero. |
| Partial execution | `benchmarks/run.py:238` records completed task attempts, but `:324` marks the schedule complete even after budget errors. Cancellation can bypass ordinary error handling and report generation at `:331`. |
| Quality metrics | `benchmarks/metrics.py:100` creates groups only from observed rows. An entirely absent engine/task is omitted. `:57` validates split coverage, but the separate exactness calculation at `:157` can disagree on duplicate segments. |
| Report | `benchmarks/report.py:39` treats every non-demo study as synthetic. Its chart at `:76` substitutes zero for missing latency. Current warmup/preparation accounting needs an explicit study-level summary. |
| Real-document foundations | `examples/real/SOURCE.json`, `examples/real/assemble.py:25`, and `tests/test_real_examples.py:16` provide provenance, preserved-page assembly, and identity checks. The real rule files already define the five categories. |
| Separate synthetic fixtures | `tests/test_dataset_integrity.py:27` deliberately forbids source reuse across tasks. Leave those tests intact and add dedicated tests for this corpus's different, explicit reuse contract. |

## Desired end state

A source checkout contains a versioned real-document corpus, provenance and checked labels, deterministic packet assembly, a frozen experiment configuration, an entirely local preparation command, and a one-pass execution command. A report regenerates offline from durable evidence, including when no measured inference succeeds.

The report answers: how many documents each engine classified correctly; how many packets it split exactly; which labels/boundaries failed; how long successful decisions took; and the observed estimated cost, with any unknown charges clearly identified. Poor accuracy is a valid outcome and does not trigger prompt tuning or another paid run.

## Implementation approach and resolved tradeoffs

- **Use a small curated corpus of authentic originals.** This follows the user's cost/speed preference. A public-corpus subset would improve comparability but introduces larger acquisition and annotation work. This pilot will be described as a convenience sample of short English public-sector PDFs.
- **Reuse originals across tasks.** This reduces sourcing and annotation work while supporting 40 classification decisions and 8 segmentation cases. Keep the two task results separate and disclose shared source/template families.
- **Prepare first, execute second.** Add a receipt-based local preparation step to the existing runner. No inference client or warmup starts before complete input validation and actual-text cost admission.
- **Show counts instead of inferential intervals for this pilot.** Classification has 2.5-percentage-point resolution; packet exact match has 12.5-point resolution. Do not headline bootstrap confidence intervals on a non-random, correlated sample of eight packets. Existing regression-study interval support need not be removed.
- **Stop instead of retrying unavailable services.** Bound one paid attempt, preserve evidence and unknown costs, and generate a partial report. Do not implement a resumable job system.

All paths below marked **new** are proposed additions. Commands using them become available during implementation. Complete the manual checks after each phase before moving on; these are implementation verification steps, not additional user approval gates.

## Phase 1: Acquire, annotate, and freeze the real corpus

### Changes required

**New:** `datasets/real-small/v1/PROTOCOL.md`, `candidates.json`, `SOURCE.json`, `annotations.json`, `exclusions.json`, `packet-plan.json`, `FREEZE.json`, `DATASET_CARD.md`, and `NOTICE.md`.

**New:** `datasets/real-small/v1/originals/e001.pdf` through `e040.pdf`; `packets/p001.pdf` through `p008.pdf`; `rules/classify.yaml`, `rules/split.yaml`; `manifests/classify.json`, `manifests/split.json`.

**New:** `datasets/real-small/prepare.py`, `tests/test_real_small_integrity.py`.

**Update:** `datasets/LICENSE` to explicitly exclude third-party real originals, including the existing real examples, from the synthetic dedication. Preserve source-specific rights notes.

1. Write the source-selection protocol before inference. Start with official government publications: distinct tax forms, financial transaction/auction reports, narrative releases, legal notices, and unrelated instructional or educational publications. Seek multiple issuers/layout families where the category allows. Exact candidate URLs and redistribution bases must be verified during acquisition; they have not yet been selected by this plan. Avoid filling a category with minor date-only revisions of one template. Authentic blank forms are acceptable and must be identified as blank forms.
2. Download only selected candidate PDFs and keep an exclusion/replacement log. Preserve complete original bytes. Do not fabricate content, generate scans, print webpages into substitute PDFs, excerpt long documents, or add title/separator pages. Reject ambiguous, incomplete, unsuitable-rights, near-duplicate, or over-budget candidates before freeze. Do not replace a source because of a model prediction.
3. Record URL, title, issuer, publication/retrieval dates, byte count, SHA-256, page count, page-content hashes, rights basis, source/template family, and completeness. An official domain alone is not evidence that every embedded asset is freely redistributable. Retain original document metadata; neutral local filenames suffice because only page text enters inference.
4. Copy the existing real rules and make only general-purpose clarifications needed for the new corpus before freeze. Preserve the distinction between auction results and narrative news releases. Treat a publication plus its supporting tables, instructions, and appendices as one source. `other` examples must fall outside all four named purposes; tax-form instructions are not `other`.
5. Annotate every source with category, short purpose evidence, supporting page references, annotator/reviewer identity and type, and resolution of disagreements. A separate review pass checks all 40 labels and source completeness from the PDFs before inference. Record agent-assisted annotation honestly; set human review to `not_performed` unless a person actually reviews it. Ground truth, titles, source paths, provenance, and packet assembly maps must never be passed to either model as extra evidence.
6. Assign five complete sources to each packet with a deterministic, recorded plan. The following category slots meet the 8-per-category balance and four same-category challenges; choose actual source assignments to fit page caps:

   | Packet | Category order |
   |---|---|
   | p001 | tax, tax, financial, press, other |
   | p002 | financial, financial, legal, tax, other |
   | p003 | press, press, tax, legal, other |
   | p004 | legal, legal, financial, press, other |
   | p005–p008 | One of each category, in four different fixed orders |

7. Derive truth segments from checked source labels and complete page mappings. Expect **40 segments and 32 internal boundaries** across the eight packets; source boundaries count even when categories match. Preserve within-source page order. Compare content, dimensions, rotation, and rendered pages after assembly so copied streams with broken resources cannot pass unnoticed.
8. Add two globally distinct `dev` manifest entries referencing the existing BEA classification document and real split packet. These create no new originals; all five old originals remain excluded from the scored corpus. Include these dependencies in freeze identity. Test manifest IDs remain globally unique across tasks.
9. Freeze sources, annotations, review status, rule files, manifests, packet plan, and assembly-tool hash. `FREEZE.json` stores their hashes without self-referential hashing. `--verify` must be offline and read-only; it must never silently update a hash to accept changed data. Later changes require a new corpus version and invalidate preparation receipts.

### Success criteria

**Automated verification**

- [x] `uv run python datasets/real-small/prepare.py --verify` confirms exactly 40 originals, five classes × eight, ≤160 unique source pages, eight five-source packets, ≤25 pages each, and required same-category adjacency in at least four packets.
- [x] `uv run pytest tests/test_real_small_integrity.py tests/test_real_examples.py tests/test_dataset_integrity.py` verifies hashes, complete coverage, exactly-once packet membership, exclusion of demo sources, unique IDs, annotation completeness, and unchanged existing fixture contracts.
- [x] Full-page render comparison confirms each assembled page matches its original under the same pinned renderer. Test fixtures cover duplicate sources, missing pages, bad labels, and changed resource/rendering content.

**Manual verification**

- [x] Review the actual 40 PDFs, not just extracted text, for authentic appearance, completeness, labels, and source/rights evidence. Check packet transitions and long supporting sections visually.
- [x] Confirm no claim of independent human annotation, unseen-template generalization, native Office accuracy, or naturally occurring packet streams. The constituent documents are authentic; packet combinations are constructed.

## Phase 2: Add enforced local preparation and actual-text preflight

### Changes required

**New:** `benchmarks/configs/real-small-v1.yaml`, `benchmarks/prepare.py`, `tests/test_benchmark_prepare.py`.

**Update:** `benchmarks/run.py`; reuse `src/jev_docs/documents.py`, `cache.py`, and `schemas.py` rather than creating another OCR representation.

1. Add the fixed profile: `experiment_kind: real-document-accuracy-pilot`, dataset version, the contract above, `scope: decision`, `ocr: liteparse`, `repeats: 1`, `warmups: 1`, `concurrency: 1`, seed `20260919`, and budget `2`. Use the normal dev warmup policy. Freeze the current rules, thresholds, price table, parser/options, installed versions, model IDs, lockfile, and prompt source. Do not silently replace model IDs if unavailable.
2. Validate final settings after all CLI overrides. For this profile, reject `--limit`, repeats other than one, cloud OCR, other models, parallel execution, retries, and increases to the fixed budget/deadlines. Other existing configurations retain their supported behavior. Validate counts, packet membership, global IDs, hash identity, and actual category balance rather than trusting config declarations.
3. Keep `--dry-run` as a cheap, network-free manifest estimate and label its per-page text assumption. Add mutually exclusive `--prepare-only` and `--prepared <receipt>` modes. Real-small live execution must require a valid prepared receipt.
4. Prepare all **48 scored task inputs plus 2 existing development inputs** locally before constructing decision clients. Use existing parse/cache semantics, record actual cache hits, and do not call cached preparation a cold OCR measurement. Run each native OCR operation in a child process with a 60-second limit; terminate, kill if necessary, and join on expiry. A timeout around `asyncio.to_thread` is insufficient to stop native OCR. Enforce a 600-second total preparation deadline.
5. Persist full parsed artifacts only under ignored `.jev-docs/benchmark-parsed/`. Produce a public-safe preparation receipt with source/canonical/text/artifact hashes, actual text bytes, page counts, parser identity/options, source-family metadata, expected observations, original timing/cache metrics, and success/error status for every input. Record preparation failures without discarding their original source IDs.
6. Validate engine payload sizes/window plans locally from the prepared text and frozen rules. Use each adapter's actual request construction/checks, not an unrelated byte heuristic that can diverge. Do not truncate input to fit. Individual frozen test OCR/context failures become explicit unsuccessful items for the relevant task/engine; they remain in the denominator. Invalid corpus identity, failed warmup preparation, or a total preparation deadline prevents all paid dispatch.
7. Compute reservations for every dispatchable warmup and measured invocation using actual text and the existing conservative pricing formulas. Retain their safety allowance. Require the complete remaining estimate plus any retained liability to fit within $2 before any warmup. Store planned versus dispatchable call counts and estimated totals. If it does not fit, stop locally; do not shrink the frozen corpus or raise the guard automatically.
8. Verify receipt hashes, artifacts, parser/code/pricing versions, config, and rules again in the live path. Include runner, preparation, metrics/report, OCR/conversion/cache, prompt, windowing, and engine source files in provenance. Live execution must neither re-OCR nor silently re-prepare changed inputs. Bind each paid attempt to the receipt and atomically claim it before first dispatch to prevent accidental repeated execution under a different output directory. No resume path in this scope.

### Success criteria

**Automated verification**

- [x] `uv run pytest tests/test_benchmark_prepare.py tests/test_benchmark.py` uses fake parsers/clients and confirms preparation, invalid receipts, and over-budget admission make **zero provider calls** and construct no inference clients.
- [x] Tests reject tampered artifacts, changed rules/config/source/code, global ID collisions, prohibited overrides, missing warmups, and reused execution receipts before dispatch.
- [x] A deliberately stalled OCR worker is terminated and reaped. Preparation errors are recorded, cache timing remains honest, and successful live consumption invokes no parser.
- [x] `uv run python -m benchmarks.run --config benchmarks/configs/real-small-v1.yaml --dry-run` shows 96 measured + 4 warmup planned task invocations, actual page counts, and no remote calls.

**Manual verification**

- [x] Review the preparation receipt's counts, text/page completeness, concrete version hashes, error entries, and total estimated reservation. A blocked receipt is a valid stop condition, not permission to bypass limits.
- [x] Confirm both engines receive identical normalized text for each task input and receive no labels or assembly metadata.

## Phase 3: Make the one paid attempt bounded and durable

### Changes required

**Update:** `benchmarks/run.py`, `src/jev_docs/engines/jev.py`, `tests/test_benchmark.py`, `tests/test_split.py`.

1. Freeze the complete execution matrix and seeded order in the manifest before any call: four task/engine groups, 96 measured observations, and four excluded warmups. Give every observation a stable ID. Warmup and test identities are separate even if their parser artifacts are reusable.
2. Pass explicit 30-second SDK request timeouts to both engines. Add a narrow Jev option disabling remote context-rejection recovery for this profile; the library default stays unchanged. Retain the existing locally determined window plan and record the option. A provider context rejection becomes a failed task, not another paid attempt.
3. Reserve before dispatch. Durably write a sanitized `dispatch_started` event, including `observation_id` and `reserved_cost_usd`, to `events.jsonl` before calling an engine, then append the terminal observation to `raw.jsonl`. Keep start events separate from scoreable final rows. Offline reporting must reconcile starts without terminal rows as uncertain liabilities using those reservations, even if the manifest's last budget snapshot predates dispatch. Record model/request IDs and numeric usage when available, never credentials or raw provider error bodies.
4. Apply a 60-second complete-task deadline and a 300-second paid-stage deadline, including warmups. Count every Jev window and baseline request within these limits. On budget denial, deadline, authentication failure, rate limit, transport timeout, or service-unavailable failure, stop scheduling new work for the whole study. A failed warmup also stops measured dispatch. Invalid/refused model output is a scored task failure and does not trigger retry, prompt adjustment, or replacement.
5. Preserve known costs from returned results/error records and retain conservative reservations when a dispatched task has uncertain usage. Jev holds completed-window records inside the task until it returns; cancellation can lose that partial telemetry. For this small study, treat the entire cancelled task as unknown and retain its reservation rather than adding a new per-request journaling API. Provider-request totals are then explicitly incomplete, not assumed zero. Mark undispatched observations with structured reasons such as preparation error, budget stop, deadline, or prior service failure.
6. Finalize as `complete` only when the full schedule finishes without a stop and every planned observation has a terminal outcome. Frozen test preparation/context failures get explicit unsuccessful terminal outcomes without dispatch; completion does not imply all inputs were usable or all predictions correct. Use `blocked` for admission failure, `stopped` for guard/service stop, and `interrupted` for handled cancellation. Keep stop reason, counts, and timestamps. A hard process kill may leave an unclosed run; offline reporting must identify it as incomplete from missing terminal events.
7. Ensure partial report generation runs in finalization even on cancellation or cleanup failure. Bound client cleanup to five seconds per client and preserve the original stop reason. Retain existing nonempty-output refusal and the receipt's single-attempt record; do not auto-resume or launch another run.

### Success criteria

**Automated verification**

- [x] A successful fake run performs exactly 100 task invocations, excludes all four warmups from quality, executes one observation per item/engine, and shares prepared text without OCR calls.
- [x] Fake timeouts, budget denial, bad credentials, rate limits, failed warmups, cancellation between paired engines, and cleanup failure all produce durable partial evidence and no subsequent dispatch.
- [x] Tests cover uncertain usage after a start event, preservation of returned request costs, cancellation mid-window with the entire task marked unknown, liability reconstruction from missing final events, and replay refusal. No live API calls are used for these tests.
- [x] Tests prove remote context recovery is off only for the new bounded profile; existing Jev local windows and ordinary recovery behavior retain their regression coverage.

**Manual verification**

- [x] Inspect a deliberately interrupted fake run: the report states the stop reason, expected versus completed counts, unknown charges, and retained reservations. Missing work must not appear as successful zero-cost/zero-latency calls.

## Phase 4: Make scoring and reports accurate for small and partial runs

### Changes required

**Update:** `benchmarks/metrics.py`, `benchmarks/report.py`, `tests/test_metrics.py`, `docs/benchmark-methodology.md`.

**New:** `tests/test_benchmark_report.py`.

1. Seed groups and expected IDs from the frozen execution matrix, not observed rows. All four groups must exist even for an empty raw log. Classification always has denominator 40 per engine; splitting always has eight packets, 40 segments, and 32 true internal boundaries per engine. Reject unexpected IDs and duplicate terminal observations instead of silently overwriting them. Only valid successful first-pass results can receive credit.
2. Refactor one per-packet validity/exactness decision shared by point estimates, error IDs, and any derived statistics. Duplicate segments, gaps, overlaps, or reordered page coverage cannot produce exact-match credit. Keep existing segment, boundary, page, and same-category metrics, including their documented empty-boundary conventions.
3. Add explicit planned, dispatched, successful, failed, blocked/skipped, and missing-terminal counts. Distinguish a source that could not be prepared from an inference failure and an observation never dispatched after a stop. All remain unsuccessful in the frozen headline denominator. Report conditional-on-success diagnostics only as supplementary metrics.
4. Show classification correct/40, accuracy, macro-F1, per-class support/confusion/errors. Show splitting exact/8, exact segment precision/recall/F1, boundary precision/recall/F1, same-category boundary recall with its actual count, page accuracy/macro-F1, and valid coverage. Store integer numerators rather than reconstructing them from rounded percentages.
5. For this profile, omit headline inferential confidence intervals and explain sample resolution and dependence. Mark repeat disagreement `not_measured` for a one-pass study. Keep the existing synthetic and demonstration report identities accurate.
6. Report OCR preparation once per actual prepared artifact, excluded warmups, and measured decisions as separate ledgers with timings, known estimated cost, and unknown-usage counts. Include configured and actual warmup counts. LiteParse API cost is zero; local compute cost is not estimated. Show the dated price snapshot and provider-reported cached/uncached token usage. Full-run known cost is a lower bound if any charge is unknown.
7. Show decision and task-wall p50/p95 only over successful complete invocations, with sample counts and failure counts adjacent. Missing latency is `n/a`, including in charts. If reporting a speed ratio, calculate it only over source-matched successful pairs and disclose that paired count; do not compare unequal partial populations. Keep OCR time separate from inference and do not label their reuse as a cold end-to-end measurement.
8. Add a real-pilot narrative: authentic originals, constructed packets, source reuse, shared issuer/template families, annotation method, uncontrolled provider caching, and short English PDF scope. Results do not establish general production accuracy, scan/Office performance, or naturally aggregated packet accuracy. Reuse existing LlamaIndex chart fonts/colors rather than restyling the source documents.
9. Keep all outputs regenerable without network or credentials: `manifest.json`, preparation receipt/ledger, `events.jsonl`, `raw.jsonl`, `summary.json`, `metrics.csv`, `report.md`, and `latency.svg`. Publish sanitized relative identities/hashes, not local full-text artifacts or machine-specific private paths.

### Success criteria

**Automated verification**

- [x] `uv run pytest tests/test_metrics.py tests/test_benchmark_report.py tests/test_benchmark.py` covers no observations, an entirely missing engine/task, one completed classification, partial split work, all-failed groups, and interrupted warmups.
- [x] All four expected groups retain 40/8 denominators. A duplicate-segment result is incorrect everywhere, including the incorrect-ID list. Unknown and missing records never inflate quality or become zero latency.
- [x] Report tests verify real-corpus wording, integer correct/total counts, actual warmup counts, all-in cost separation, source reuse, no pilot bootstrap headline, no synthetic boilerplate, and offline regeneration.

**Manual verification**

- [x] Read one complete fake report and one partial fake report as an external reader. The corpus size, stop/completion status, observed population for timing, cost uncertainty, and quality counts should be obvious.
- [x] Inspect the rendered chart for readable labels and explicit unavailable values under the existing brand style.

## Phase 5: Execute once, inspect errors, and package the findings

This phase executes the one scoped study only after the prior phases and local receipt checks pass. No minimum accuracy or Jev speedup is an acceptance condition.

### Changes required

**New:** `benchmarks/results/real-small-v1-<run-id>/` with recorded evidence and generated outputs.

**Update:** `README.md`, `docs/benchmark-methodology.md`, and `datasets/real-small/README.md` with the actual run status and links. The frozen v1 dataset card remains immutable so reporting updates do not invalidate corpus identity. Update the source release archive if producing the next publishable bundle; retain existing video and demonstration evidence unchanged.

1. Run the targeted checks above, then the repository's existing offline quality gates:

   ```sh
   uv sync --all-extras --locked
   uv run ruff check .
   uv run mypy src/jev_docs
   uv run pytest -m "not live"
   uv build
   ```

2. Prepare locally into a new preflight directory:

   ```sh
   uv run python -m benchmarks.run --config benchmarks/configs/real-small-v1.yaml --prepare-only --output output/real-small-v1-preflight
   ```

3. Review its receipt and recorded errors, actual page/text totals, unchanged frozen identities, estimated cost, and deadlines. If blocked, deliver the preparation findings; do not bypass the guard. If ready, run one attempt with credentials supplied only through the existing environment:

   ```sh
   uv run python -m benchmarks.run --config benchmarks/configs/real-small-v1.yaml --prepared output/real-small-v1-preflight/preparation.json --output benchmarks/results/real-small-v1-run01
   ```

4. Regenerate the report offline and inspect first-pass errors against the original PDFs, frozen labels, and saved results. Describe error patterns without changing labels/rules or rerunning to improve the numbers. If review reveals a genuine annotation defect, disclose it and retain the original run; a corrected dataset/run is separate work.
5. Publish the dataset card, attribution, frozen configuration, sanitized evidence, and report in the repository bundle. Keep full extracted text caches and credentials excluded. Verify new results/data are included in the source checkout/archive and do not unintentionally inflate the package wheel. Do not publish to GitHub, PyPI, or social accounts as part of this benchmark step.

### Success criteria

**Automated verification**

- [ ] Offline quality gates pass. Full report regeneration produces the same metrics from recorded files without keys or network access.
- [ ] Published artifact checks verify hashes, JSON/CSV counts, working links, and absence of secrets or private absolute paths. New corpus files retain their source-specific rights notes.
- [ ] A completed run has all 96 measured terminal outcomes and four terminal warmups; a stopped run accurately identifies every unattempted or uncertain observation. Provider-request count is reported separately and may exceed task count.

**Manual verification**

- [ ] README claims match actual correct/40 and exact/8 counts and actual elapsed/cost data. No result is presented as a broad accuracy or unconditional speed claim.
- [ ] Review all failed/incorrect cases and several successful cases against original pages. The final deliverable is useful even if performance is poor or the guard stops execution.

## What we're NOT doing

- No synthetic documents or artificial scans in this accuracy set; no redesign of authentic source pages.
- No 200-document study, full public-corpus download, cloud/VLM OCR sweep, Office/handwriting/multilingual benchmark, additional baselines, repeated timing sweep, or throughput experiment.
- No training, prompt search, threshold tuning, test-dependent replacements, automatic reruns, or budget/deadline increases.
- No new general experiment framework, resumable scheduler, dashboard, or video revision.
- No claims about unseen issuers/templates, human-adjudicated labels, representative customer workloads, or independent samples across the two tasks.
- No external publication or additional paid experiment beyond the single scoped run during implementation.

## Testing strategy and execution order

Corpus/provenance and frozen-rule work comes first. Local preparation and admission come next. Runner durability and scoring/report work can proceed independently against fake data once the manifest/observation contracts are fixed. Integrate and complete offline verification before sourcing any live result.

Tests should target failure modes that change spend or conclusions: no paid work on blocked admission, no hidden OCR/retries, deadline cleanup, uncertain charges, denominator preservation, invalid segmentation, and offline reproducibility. Do not add snapshot tests that merely mirror report formatting or tests requiring current external document URLs. Default CI remains network-free and makes no paid API calls.

## References

- Scope decision: `research/2026-09-19-real-document-evaluation-options.md:16`.
- Existing harness audit: `research/2026-09-19-accuracy-run-scope.md`.
- Current real-demo protocol: `benchmarks/configs/real-doc-pilot.yaml` and `docs/benchmark-methodology.md`.
- Execution/preparation: `benchmarks/run.py:109`, `:150`, `:195`, `:293`, `:324`.
- Metrics/report behavior: `benchmarks/metrics.py:48`, `:100`, `:157`; `benchmarks/report.py:19`.
- Existing authentic-source patterns: `examples/real/SOURCE.json`, `examples/real/assemble.py`, `tests/test_real_examples.py`.
- Existing category definitions: `examples/real/classify/rules.yaml`, `examples/real/split/rules.yaml`.

## Implementation evidence

- Initial DocJev commit `3a68115` was pushed to `jerryjliu/docjev`; its GitHub Actions run passed. Benchmark changes remain local under the plan’s publication boundary.
- Corpus: 40 originals, 116 unique pages, 232 scored task-input pages, eight packets, 40 segments, 32 boundaries, four same-category boundaries. All assembled pages pass rendered pixel equality. Source/label reviews were performed by agents, not by a human.
- Offline gates: locked dependency sync, Ruff, typing for library and benchmark modules, 177 offline tests, and wheel/source builds passed. Root-level QA exclusion was added after archive inspection caught local galleries in the first source build; the corrected source build includes all originals/packets and excludes QA, while the wheel excludes the evaluation corpus.
- Preparation: 50/50 inputs and 100/100 adapter preflight checks passed in 56.57 seconds, with two cache hits, zero remote calls, 257 pages including warmups, and no empty-text pages. Actual-text reservation: $0.776979 under the $2 local estimated guard. Receipt validation confirmed source, page, artifact, parser, rules, code, package, and execution-matrix identity before dispatch.
- Manual verification checkboxes record implementation reviews by the agents under the plan’s instruction that these are verification steps, not additional user approval gates. Human annotation/review is not claimed.

---
date: 2026-09-19T09:08:16-07:00
git_commit: null
branch: main
repository: 2026_09_18_jev_doc_classify_splitting
topic: "Existing scope for a Jev document classification and splitting accuracy run"
tags: [research, accuracy, evaluation, datasets, jev, liteparse, benchmarks]
status: complete
last_updated: 2026-09-19
last_updated_by: codex
---

# Research: accuracy-run scope

## Research Question

What accuracy evaluation can the current repository execute, what has actually been measured, and what is still undefined for a real-document accuracy study?

This is a read-only investigation of the current implementation, manifests, recorded results, and tests. Three local dry runs and offline tests were executed; no inference requests, dataset changes, or implementation changes were made. The repository is on `main` with no commit yet, so there is no resolvable commit identifier. File-and-line references describe the working tree inspected on September 19, 2026.

## Summary

- **A bounded synthetic accuracy comparison is executable now:** 48 classification documents and 18 splitting packets, evaluated by both Jev and the small LLM baseline. One measured pass covers those same 66 test units as five passes; subsequent passes add latency and consistency observations, not independent accuracy examples. The full synthetic study remains unrun. [Default configuration](../benchmarks/configs/default.yaml#L1), [first-pass scoring](../benchmarks/metrics.py#L100), [recorded study status](../docs/benchmark-methodology.md#L5).
- **The completed real-document run is a demonstration pilot:** one ten-page BEA release and one fifteen-page packet, three timed repetitions per engine/task, and four excluded warmup calls. Both engines matched each declared first-pass answer, reported as **1/1 per task**. This does not measure held-out real-document accuracy. [Pilot report](../benchmarks/results/real-doc-pilot-20260919/report.md#L3), [pilot configuration](../benchmarks/configs/real-doc-pilot.yaml#L1).
- **Five real original PDFs are available, but only one classification original is in the benchmark configuration.** The packet reuses four of the five originals, including the measured classification document. No larger independently labeled real-document evaluation corpus or adjudication record was found among the inspected datasets, examples, and benchmark artifacts. [Real originals](../examples/real/demo-manifest.json#L2), [real benchmark input](../benchmarks/manifests/real-classify.json#L3), [packet input](../benchmarks/manifests/real-split.json#L3).
- **Metrics distinguish label correctness from segmentation correctness** and retain first-pass failures in the planned denominator. Decision latency excludes OCR; successful-call latency, failure counts, token costs, and OCR preparation are recorded separately. The current results measure this application's OCR-plus-rules-plus-decision behavior, not OCR transcription accuracy or model confidence calibration. [Scoring](../benchmarks/metrics.py#L48), [OCR preparation](../benchmarks/run.py#L195), [review threshold](../src/jev_docs/classify.py#L51).

## Detailed Findings

### 1. Existing executable scope

The following counts were verified with the existing `--dry-run` interface. Every invocation returned `remote_calls: 0` and validated current source hashes. Estimates are local reservation estimates, not quotes or billing caps. They include excluded warmup task calls. The underlying formula assumes 12,000 OCR bytes per page before actual parsing. [Loader](../benchmarks/run.py#L88), [reservation calculation](../benchmarks/run.py#L109), [dry-run output](../benchmarks/run.py#L128).

| Existing condition | Independent scoring units per task | Measured task calls across both engines | Excluded warmup calls | Local estimated reservation |
|---|---|---:|---:|---:|
| Synthetic default, five passes | 48 classification documents; 18 packets | 660 | 12 | $7.490787 against a $10 guard |
| Same synthetic inputs, one pass | 48 classification documents; 18 packets | 132 | 12 | $1.641539 against a $10 guard |
| Existing real demo, three passes | 1 classification document; 1 packet, overlapping source content | 12 | 4 | $0.426912 against a $2 guard |

“Independent scoring units” here means distinct manifest documents or packets, not statistical independence of their language or templates. A task call can contain multiple provider requests when Jev splits work into windows or recovers from a context-size rejection. [Jev splitting](../src/jev_docs/engines/jev.py#L163).

Commands actually used for this research:

```sh
uv run python -m benchmarks.run --config benchmarks/configs/default.yaml --dry-run
uv run python -m benchmarks.run --config benchmarks/configs/default.yaml --repeats 1 --dry-run
uv run python -m benchmarks.run --config benchmarks/configs/real-doc-pilot.yaml --dry-run
```

The same interface executes a run when `--dry-run` is absent and accepts a new `--output` directory. The CLI supports a repeat count, a prefix limit per task, decision or end-to-end scope, and concurrency 1 or 4. `--limit` selects the first manifest test items; it is not a random or stratified sample. The runner always constructs both engines; it has no Jev-only command-line mode. Existing output directories containing data are rejected, and there is no resume switch. [CLI](../benchmarks/run.py#L334), [prefix limit](../benchmarks/run.py#L95), [run initialization](../benchmarks/run.py#L150).

Default settings are LiteParse, Jev `jev-1.13.0`, baseline `gpt-5.6-luna`, sequential execution, no SDK/application retries, a boundary threshold of 0.5, and an operational review threshold of 0.7. The baseline whitelist also accepts `gpt-4o-mini` and its listed snapshot. [Configuration](../benchmarks/configs/default.yaml#L1), [configuration validation](../benchmarks/run.py#L69).

### 2. Synthetic corpus and source separation

The synthetic manifests provide the following fixed assets. Counts were obtained from the current JSON manifests and agree with the generator and integrity checks. [Dataset card](../datasets/DATASET_CARD.md#L7), [classification generator](../datasets/generate.py#L276), [packet generator](../datasets/generate.py#L298).

| Task | Development | Test | Coverage |
|---|---|---|---|
| Classification | 12 documents, 18 pages | 48 documents, 66 pages | Six classes, eight test documents each; test set has 42 PDFs including 12 scans, plus six DOCX files |
| Splitting | Six packets, 61 pages | 18 packets, 181 pages | Six labels, 9–12 pages per packet; all PDF; three test packets are rasterized scans |

Classification labels are `invoice`, `purchase_order`, `contract`, `resume`, `pitch_deck`, and `other`. Splitting labels are `claim_form`, `incident_report`, `repair_estimate`, `invoice`, `correspondence`, and `other`. Across all 24 packets there are six deliberately blank pages, five scanned packets, and a pair of adjacent distinct invoices in every packet. There is no training partition. Native PPTX exists in demos and related format fixtures, not the quantitative corpus; those related fixtures explicitly exclude themselves from accuracy. [Dataset coverage](../datasets/DATASET_CARD.md#L12), [format-fixture exclusion](../tests/test_dataset_integrity.py#L104).

Source IDs are disjoint across synthetic classification, packets, development/test partitions, and demos. Named development/test layout families are disjoint; tests enforce these properties, and the generator separately verifies hashes and coverage. [Isolation test](../tests/test_dataset_integrity.py#L27), [generator verification](../datasets/generate.py#L399).

This separation has a specific limit: all partitions reuse the category prose templates in `content()`. Packet category order is largely fixed, with optional `other` inserts. The represented language is fictional equipment/service business paperwork and a water-damage claim pattern. Synthetic scans are grayscale renders at scale 1.55, slightly rotated and blurred; they are not a collection of naturally photographed or handwritten documents. Distinct source IDs and layout families therefore do not establish independent language-template or real-domain generalization. [Shared prose](../datasets/generate.py#L74), [packet order](../datasets/generate.py#L303), [scan generation](../datasets/generate.py#L193).

Ground truth follows category arguments and packet assembly offsets. The dataset card describes human-authored templates; the inspectable implementation establishes deterministic source-derived labels. It does not contain an independent annotator/adjudicator record. [Ground-truth description](../datasets/DATASET_CARD.md#L18), [label assignment](../datasets/generate.py#L288), [boundary assignment](../datasets/generate.py#L314).

### 3. Real-document assets and measured evidence

The real demo contains five original PDFs totaling 17 pages: IRS Form 941, two Treasury auction reports, a BEA release, and an SEC notice. Their labels cover `tax_form`, `financial_report`, `press_release`, and `legal_notice`; there is no real `other` example, scan, or native Office example. The fifteen-page packet concatenates the IRS form, the two separate auction reports, and the complete BEA release. Its ground-truth boundaries are the original-file boundaries, including the adjacent auction reports. [Original manifest](../examples/real/demo-manifest.json#L2), [assembly mapping](../examples/real/demo-manifest.json#L94), [provenance tests](../tests/test_real_examples.py#L16).

Original byte hashes, page-content hashes, issuer/source URLs, and source-to-packet page mappings are recorded. Tests check those identities and segment mappings. Category interpretations are explicit in the rules: Treasury auction sheets are `financial_report` despite news headers; the IRS voucher remains with its form; BEA technical notes and appendices remain with the release. These records establish provenance and declared semantics, not independent semantic adjudication. [Page-preservation test](../tests/test_real_examples.py#L33), [classification rules](../examples/real/classify/rules.yaml#L2), [splitting rules](../examples/real/split/rules.yaml#L12).

The canonical real demo manifest is an object with `classify` and `split` arrays. The benchmark loader instead consumes one array per configured task. Its real classification array currently contains only `r04`, and its split array contains only `real-finance-packet`. Both carry `split: test` for runner selection while explicitly declaring `sample_purpose: demonstration only`; the configuration separately declares demonstration scope and intentionally reuses those sources for warmups. [Benchmark classification manifest](../benchmarks/manifests/real-classify.json#L3), [benchmark split declaration](../benchmarks/manifests/real-split.json#L133), [warmup selection](../benchmarks/run.py#L103).

Only `real-doc-pilot-20260919` is present as a recorded run under `benchmarks/results/`, alongside its copied latest summary. Inspection of its raw observations found **16 successful provider requests: four warmups and twelve measured calls**. Each engine agreed with the one classification label and one packet assembly on the first measured pass, with no repeat disagreement. The reported medians are 182.5 ms versus 785.4 ms for classification and 293.8 ms versus 1,590.8 ms for splitting, Jev versus Luna. Total estimated run cost including warmups is $0.016941402. [Recorded report](../benchmarks/results/real-doc-pilot-20260919/report.md#L5), [run totals](../benchmarks/results/real-doc-pilot-20260919/manifest.json#L311).

The recorded machine is macOS arm64 with Python 3.12.6 and LiteParse 2.14.6. All eight recorded decision-source/pricing hashes still match the inspected files. The single-source confidence intervals are null, not meaningful generalization intervals. Luna's measured input was almost entirely cached and its measured API cost was lower than Jev's; this is part of the repeated-input condition. [Environment/hashes](../benchmarks/results/real-doc-pilot-20260919/manifest.json#L199), [cache counts](../benchmarks/results/real-doc-pilot-20260919/report.md#L29), [interval convention](../benchmarks/metrics.py#L92).

### 4. Execution and data flow

1. Configuration selects task-specific manifests and rule files. The loader checks source byte hashes before execution. The run manifest captures datasets, configuration, model requests, package/machine versions, lockfile hash, selected inference source hashes, and rule/input-manifest hashes. [Loading](../benchmarks/run.py#L88), [provenance](../benchmarks/run.py#L150).
2. In decision scope, each manifest ID is parsed once and memoized. Parsed page count and source hash are checked against the manifest. Normalized pages are hashed; full parsed artifacts remain under ignored `.jev-docs/benchmark-parsed/`. Preparation telemetry is retained, then OCR cost/time/request records are reset before reuse by either engine. Existing OCR cache entries can supply that preparation. [Preparation](../benchmarks/run.py#L195), [OCR cache](../src/jev_docs/documents.py#L64).
3. Engine inputs contain page number, text, and verified-blank state, plus natural-language rules. They do not receive the manifest's expected labels, assembly map, title, source filename, or source IDs. Jev classification asks one category question over all pages. Jev splitting asks page categories and boundaries, initially attempting the whole packet and using bounded windows when necessary. The baseline requests a single structured category or complete contiguous segment list. [Shared page state](../src/jev_docs/engines/base.py#L23), [Jev classification](../src/jev_docs/engines/jev.py#L117), [Jev splitting](../src/jev_docs/engines/jev.py#L138), [baseline request](../src/jev_docs/engines/openai.py#L37).
4. Both outputs pass through the application. Category changes can force segment boundaries; verified blanks are assigned `other` and remain represented. Therefore split quality evaluates the final application result, including deterministic assembly, rather than raw boundary questions alone. [Segment assembly](../src/jev_docs/split.py#L16).
5. The runner performs excluded warmups, then shuffles test-unit order and provider order within each pair with a fixed seed. Clients are reused. Every completed attempt appends and flushes a raw observation, including errors. Reports regenerate from those observations without inference. [Scheduling](../benchmarks/run.py#L291), [recording](../benchmarks/run.py#L273), [report generation](../benchmarks/report.py#L19).

End-to-end scope takes raw paths and disables OCR/conversion cache reuse for each task invocation. It is supported by the implementation but was not the recorded pilot condition. Neither scope performs text-transcription scoring: unreadable nonblank pages fail parsing, but there is no ground-truth OCR transcript metric. [Scope switch](../benchmarks/run.py#L250), [page validation](../src/jev_docs/documents.py#L16).

### 5. What the accuracy metrics mean

| Metric | Current meaning |
|---|---|
| Classification accuracy, macro-F1, per-class precision/recall/F1 | First measured pass, every planned test document; absent/failed predictions are missing rather than removed |
| Packet exact match | Entire set of category-plus-page-range segments matches ground truth |
| Page accuracy / macro-F1 | Correct category per page; invalid or failed packets have no predicted pages |
| Boundary precision/recall/F1 | Correct segment starts after page one, regardless of category correctness |
| Segment precision/recall/F1 | Exact category and complete page range together |
| Same-category boundary recall | True boundaries between neighboring sources with the same category that were recovered |
| Coverage validity | Predicted ordered segments cover every page exactly once |
| Repeat disagreement | At least two successful repetitions of a source return different labels/segmentations |

These definitions come directly from [label scoring](../benchmarks/metrics.py#L29), [split scoring](../benchmarks/metrics.py#L48), and [summary construction](../benchmarks/metrics.py#L100). A missed boundary between two invoices can have perfect page-category accuracy while failing exact packet match; the hand-computed test explicitly verifies this. [Boundary test](../tests/test_metrics.py#L29).

Failed, unreadable, refused, over-limit, or budget-blocked first-pass inputs remain in the denominator. For each observed task/engine/model group, missing first-pass IDs are inserted as unsuccessful observations. A group with no measured rows at all is not synthesized by `summarize`, so a completely absent group has no summary entry. Macro-F1 covers labels occurring in ground truth, rather than every configured rule category. The current real classification pilot therefore measures only `press_release` quality. [Missing observations and grouping](../benchmarks/metrics.py#L100), [label selection](../benchmarks/metrics.py#L146).

Bootstrap intervals resample document/packet correctness from the first pass, with 2,000 draws; fewer than two units yields null. They do not resample semantic template families, and do not supply uncertainty intervals for latency, F1, or speed ratios. The review threshold is operational, not calibrated; the baseline returns no category probabilities. [Bootstrap](../benchmarks/metrics.py#L92), [baseline category output](../src/jev_docs/engines/openai.py#L128), [review semantics](../src/jev_docs/classify.py#L51).

### 6. Latency, cost, and operational limits

`decision_ms` spans the complete engine operation, including all windows and size-recovery attempts; validation follows it. `wall_ms` spans the scoped task invocation, excluding preparation in decision scope and including fresh OCR in end-to-end scope. Reported p50/p95 use successful full-task calls across all measured repetitions. Failed calls have recorded wall times and counts but are excluded from those latency quantiles. [Classification timing](../src/jev_docs/classify.py#L39), [split timing](../src/jev_docs/split.py#L90), [runner clock](../benchmarks/run.py#L256), [latency aggregation](../benchmarks/metrics.py#L112).

Known measured decision cost sums recorded request estimates, excluding OCR and warmups. The run budget includes warmups and paid OCR preparation. Unknown request usage remains unknown and retains a reservation; failed dispatched calls without usable records count as unknown-cost calls. Price constants are implemented in the engines and mirrored by the recorded `pricing.json`; the JSON file is provenance rather than a dynamically loaded pricing engine. [Cost aggregation](../benchmarks/metrics.py#L116), [budget ledger](../benchmarks/run.py#L36), [Jev cost](../src/jev_docs/engines/jev.py#L95), [baseline cache-aware cost](../src/jev_docs/engines/openai.py#L79), [price snapshot](../benchmarks/pricing.json#L1).

The comparison uses practical task implementations, with distinct prompt/output shapes. There is no matched per-page-decision mode. Provider cache state, service load, network conditions, and geography are uncontrolled; process-cold behavior is not measured. Concurrency four is one shared semaphore across both providers, not separate per-provider throughput isolation. Jev enforces byte-budget checks and can shrink splitting windows; classification has no long-document chunk aggregation. The baseline has a 500,000-byte supported payload limit. Neither silently truncates to fit. [Run protocol](../benchmarks/run.py#L174), [shared semaphore](../benchmarks/run.py#L184), [context budgets](../src/jev_docs/windows.py#L9), [baseline size check](../src/jev_docs/engines/openai.py#L40).

### 7. Verification performed in this research

- Three local dry runs verified source hashes and the call/budget counts above, without provider access.
- Nine offline metric/recorder tests passed. They cover hand-computed failures, same-category boundaries, invalid coverage, zero-boundary conventions, first-pass denominators, repeated latency observations, unknown-cost reservations, shared OCR artifacts, and no historical OCR double-counting. These are implementation checks, not model accuracy measurements. [Metric tests](../tests/test_metrics.py#L19), [recorder tests](../tests/test_benchmark.py#L12).
- Independent dataset inspection ran ten dataset/provenance tests successfully, covering file identity, partition separation, page coverage, scans, excluded related fixtures, and authentic original/packet mapping. [Synthetic integrity tests](../tests/test_dataset_integrity.py#L16), [real provenance tests](../tests/test_real_examples.py#L16).
- Existing pilot observations and source hashes were read and checked. No new full synthetic, real-document, end-to-end, cloud-OCR, or concurrency-four inference run was performed.

## Code References

| Component | Entry points |
|---|---|
| Executable benchmark scope | [default config](../benchmarks/configs/default.yaml#L1), [real pilot config](../benchmarks/configs/real-doc-pilot.yaml#L1), [CLI](../benchmarks/run.py#L334) |
| Input and execution contracts | [manifest loader](../benchmarks/run.py#L88), [OCR preparation](../benchmarks/run.py#L195), [attempt recorder](../benchmarks/run.py#L238) |
| Task semantics and inference | [shared instructions](../src/jev_docs/engines/base.py#L7), [Jev](../src/jev_docs/engines/jev.py#L117), [baseline](../src/jev_docs/engines/openai.py#L128), [assembly](../src/jev_docs/split.py#L16) |
| Scoring and reporting | [metrics](../benchmarks/metrics.py#L29), [report](../benchmarks/report.py#L19), [metric tests](../tests/test_metrics.py#L19) |
| Dataset lineage | [synthetic generator](../datasets/generate.py#L276), [synthetic card](../datasets/DATASET_CARD.md#L18), [real originals](../examples/real/demo-manifest.json#L2), [real packet test](../tests/test_real_examples.py#L33) |

## Architecture Notes

The reusable unit between OCR and inference is `ParsedDocument`; the benchmark shares its normalized ordered pages across providers and isolates current-call metrics from historical preparation. Ground truth lives outside the inference path. Source identity, declared category, and exact original-file boundaries are separate concepts: distinct manifest IDs can still share semantic templates, and the real classification input is also part of the splitting packet. Accuracy aggregation uses documents/packets; page and segment metrics provide additional detail but do not increase the number of independent source examples.

The loader accepts task-specific manifest arrays, verifies bytes, and assumes their labels and source metadata are valid. Dataset independence is established by the included generator/integrity tests, not by a generic source-overlap or annotation-validation step in the runner. The prepared-document cache is keyed by manifest ID across tasks. [Loader](../benchmarks/run.py#L88), [cache key](../benchmarks/run.py#L195), [independence tests](../tests/test_dataset_integrity.py#L27).

Report prose currently distinguishes `experiment_kind: demonstration` from all other runs, which it describes as synthetic. Its demonstration introduction specifically describes the existing one-document/one-packet, three-repeat pilot. These are the two presentation conditions currently encoded in the reporter; a general real held-out study is not represented by a separate report narrative. [Report condition](../benchmarks/report.py#L39).

## Open Questions

These are undefined study properties in the current assets, not implementation proposals:

1. **Intended accuracy claim:** controlled synthetic task correctness, a particular real business domain, or a broader document population? The current synthetic corpus and government-publication demos represent different categories and distributions.
2. **Real evaluation population and independent sample count:** no larger real manifest, sampling frame, held-out rule-development set, or cross-source/template sampling record is present.
3. **Ground-truth authority:** category definitions and original-file boundaries are explicit, but independent label review, disagreement resolution, and treatment of ambiguous compound documents are not recorded.
4. **OCR condition:** current completed measurements use LiteParse. Accuracy differences among local OCR and the three LlamaParse tiers, and any transcription-quality contribution, have not been measured over this corpus.
5. **Breadth and acceptance criteria:** no declared minimum accuracy, tolerance for boundary errors, calibrated review/abstention target, or confidence-interval precision requirement defines success for a new real study. Current data do not quantify native PPTX, natural scan/photo, handwriting, multilingual, or arbitrary long-document performance.
6. **Model-training exposure:** repository source separation is inspectable; whether any public original appeared in either provider's training data is unknown.
7. **Unperformed comparison conditions:** the full synthetic evaluation, broader real accuracy run, end-to-end comparison, process-cold measurements, matched-decision comparison, and separate throughput study have no recorded result in the inspected benchmark outputs.

## Follow-up: public real-document dataset options

A separate [source-backed dataset survey and proposed first-study scope](2026-09-19-real-document-evaluation-options.md) compares RVL-CDIP, DocSplit, TABME++, and WooIR. It distinguishes natural streams from constructed packets of real pages and proposes a held-out corpus, annotation procedure, OCR conditions, and reporting scope. No external dataset or full accuracy run was executed.

# Benchmark methodology

The harness measures authentic provider calls and preserves each observation. A report is evidence for its declared documents, models, OCR, client/network conditions, and sample count. The small synthetic corpus and a real-document video pilot are separate conditions; neither establishes a general speedup across workloads.

The completed [real-document pilot](../benchmarks/results/real-doc-pilot-20260919/report.md) uses one ten-page BEA release and one 15-page packet, three timed repeats, and one excluded warmup per engine/task. Both matched 1/1 declared sources. Jev median decision times were 182.5 ms for classification and 293.8 ms for splitting; Luna's were 785.4 ms and 1,590.8 ms. Repeated Luna input was almost entirely served from its input cache and cost less in the measured portion. The full synthetic evaluation remains unrun.

The separate [40-original / eight-packet accuracy pilot](../benchmarks/results/real-small-v1-run01/report.md) completed one pass: both engines classified 40/40, while Jev split 7/8 exactly and Luna split 8/8. All 100 tasks including warmups completed for an estimated $0.068050. The [error review](../benchmarks/results/real-small-v1-run01/error-analysis.md) documents the extra attachment boundary without changing frozen truth or rerunning.

## Running and regenerating

```sh
uv run python -m benchmarks.run --config benchmarks/configs/default.yaml --dry-run
uv run python -m benchmarks.run --config benchmarks/configs/default.yaml --output benchmarks/results/my-run
uv run python -m benchmarks.report benchmarks/results/my-run
```

`--dry-run` validates source-file hashes and reports planned calls and an estimated budget reservation without remote calls. Execution needs TypeSafe and OpenAI credentials in the environment. Use a new output directory for each run; existing data is never overwritten. `--limit 1 --repeats 3` creates an explicitly labeled small pilot. `--scope end-to-end` measures new OCR from raw files. `--concurrency 4` is a separate mixed-provider throughput condition; the default sequential condition remains primary.

To reproduce the real-document condition, use `--config benchmarks/configs/real-doc-pilot.yaml` and a new output directory. It reserves a maximum estimated $2 locally and declares `demo_set: real`, `experiment_kind: demonstration`, and `warmup_policy: reuse-demo-sources`. Those warmups intentionally reuse the demo inputs; they are not a held-out evaluation.

## Small real-document accuracy profile

`benchmarks/configs/real-small-v1.yaml` defines a separate curated accuracy pilot: 40 complete English public-sector originals, eight per category, reused exactly once across eight constructed packets of five originals. The study has 40 unique source documents and 48 scored task inputs. It does not have 48 independent sources, and the classification and splitting results must not be pooled. Shared issuer/template families can also correlate errors. Annotation is agent-assisted; human review must remain recorded as not performed unless it actually occurs.

The profile performs one measured pass: 96 planned task invocations across two engines, plus four excluded warmup invocations using two existing development inputs outside the scored set. A task can contain multiple predetermined Jev requests. It uses shared LiteParse preparation, concurrency one, zero retries, a $2 local estimated guard, and fixed preparation/request/task/stage deadlines. It does not include the larger synthetic study or a repeated timing sweep.

Use the local `--prepare-only` mode first, then provide its receipt with `--prepared` for the single admitted attempt. Preparation receipts freeze identity, actual parsed text sizes, cache state, failures, and estimated reservations; live execution does not silently reparse changed inputs. A blocked or interrupted study is still reportable. Reusing a receipt for another paid attempt is outside this protocol.

The real accuracy report shows raw correct/40 and exact/8 counts, descriptive percentages, and successful-call latency quantiles. Classification has 2.5-percentage-point resolution and packet exact match has 12.5-point resolution. Inferential intervals are omitted for this non-random, dependent sample; existing source-bootstrap outputs for the separate synthetic/demo conditions remain available. Repeat disagreement is not measured in a one-pass study. This convenience sample cannot establish production accuracy, unseen-template generalization, scan/Office performance, or performance on naturally aggregated packets.

## Frozen inputs and shared OCR

The manifest captures source hashes, rules, parser/options, model requests, SDK versions, lockfile and prompt-source hashes, operating-system/runtime information, and seeded execution settings. It verifies input files against frozen dataset manifests before any paid calls. Ground truth, source filenames, and assembly maps never enter engine prompts.

In decision scope, each source is parsed once. Both engines receive the same ordered normalized page representation, identified by a SHA-256 hash. The original preparation timings and usage are retained in the run manifest; decision-call inputs carry zero current OCR cost and time. Local full artifacts stay under the ignored `.jev-docs/benchmark-parsed/` directory. Reports do not republish extracted full document text.

In end-to-end scope, each call begins from the raw input, with OCR and Office cache reuse disabled and LlamaParse server cache disabled. Canonical PDFs remain available for source identity. Measured task wall time includes fresh conversion, OCR, decisions, and validation; export is excluded. Decision-only totals must never be presented as complete OCR-to-result latency.

## Calls and timing

The standard synthetic protocol has 48 classification test sources and 18 splitting test packets, five measured passes, and three excluded development warmups per engine/task. Provider order within each document pair and document order are shuffled with a fixed seed. Clients are reused after warmups; provider cold/cache state and network variability are not controlled. Separate process-cold performance is not measured. A video pilot may use fewer documents/passes/warmups, and records that scope explicitly.

The baseline efficiently returns one document category or a whole packet's contiguous segments in one call when supported. Jev uses categorical and boundary questions with bounded windows, including same-category document boundaries. Both produce the same task output. This is a practical implementation comparison, not a matched per-page request experiment. All SDK/application retries are disabled in the benchmark. Provider size-recovery attempts remain visible in request records.

`decision_ms` covers every inference request/window through the engine call. `wall_ms` measures the actual scoped task invocation, not projected sums from historical OCR. Report p50 and p95 over successful complete document/packet calls, alongside failures and sample counts. Five repetitions improve timing observations but do not create five independent accuracy examples.

## Quality and costs

Classification accuracy/macro-F1 and packet exact match use the first declared measured pass and every frozen test source as the denominator, including missing, failed, refused, over-limit, and unreadable inputs. Splitting additionally measures page accuracy/macro-F1, boundary precision/recall/F1 excluding the first page, exact category-plus-range segment F1, valid coverage, and adjacent same-category boundary recall. Failed or invalid packets provide no predicted pages/segments. No predicted or true boundaries yields boundary F1 1; missed real boundaries yield recall 0. No same-category boundary in the truth yields null for that specialized recall.

For synthetic and demonstration conditions, bootstrap intervals resample whole source documents or packets; fewer than two unique inputs yield no interval. The curated real accuracy profile omits these intervals. Repeats never change quality denominators. Reports retain integer correct counts, per-class support/confusion matrices, failed/incorrect IDs, and repeated-output disagreement where repeated observations exist. The same coverage-validity decision determines packet exact match and its incorrect-ID list; duplicated, reordered, overlapping, or incomplete segmentation receives no credit.

Costs use reported token/credit counts and the frozen `benchmarks/pricing.json` snapshot. Provider input-cache reads/writes are distinguished where available. Unknown usage remains unknown; known-cost totals are lower bounds when any charge is unknown. OCR preparation, measured inference, and excluded warmup costs have separate provenance. The run budget includes warmups and optional paid OCR, while the headline measured inference table excludes warmups. Study-level component ledgers show preparation once per task-input artifact, actual warmup calls, and measured decisions separately. Cached historical OCR charges are not rebilled; cached preparation is not cold OCR. LiteParse has zero API cost; local compute is not priced. Known partial request costs are retained even when remaining usage is unknown. A dispatch start without a trustworthy terminal observation preserves unknown liability and an incomplete request count, including when a later placeholder incorrectly claims no dispatch.

A $10 default local guard reserves an estimated conservative allowance before paid dispatch, retains reserves for unknown charges, and counts concurrent reservations. It is not a guaranteed provider billing cap: token estimates, dynamic window recovery, and delayed billing are imperfect. The dry-run assumption is 12,000 normalized OCR bytes per page; actual dispatch uses observed text sizes for the baseline. Review and add a current price/reservation entry before using a different baseline. Infrastructure costs and account-specific discounts are excluded.

## Artifacts and reproducibility

The bounded real profile writes its complete execution matrix before dispatch, then flushes a `dispatch_started` event to `events.jsonl` before each engine invocation and a terminal observation to `raw.jsonl` afterwards. `manifest.json` records configuration, environment, input identity, preparation, and budget progress. `summary.json`, `metrics.csv`, `report.md`, and a branded `latency.svg` regenerate entirely from local evidence without credentials or API calls. Older runs without an execution matrix remain readable.

For planned runs, all four task/engine groups remain in the report even when the raw log is empty. Missing, skipped, preparation-failed, and inference-failed items remain unsuccessful in the frozen denominators; repeated success cannot rescue a failed first pass. The report distinguishes planned, dispatched, successful, failed/invalid, skipped, and missing-terminal counts. A missing successful latency is `n/a`, including in charts. A hard kill may leave an unfinished final JSONL record: regeneration reports that truncation, retains earlier complete records, and marks the evidence incomplete. Interior corruption and duplicate/unexpected observations are rejected. Request IDs and numeric telemetry are retained; API keys, full text caches, and raw provider exception bodies are excluded.

Public model latency varies with document length, question count, provider load, client location, network, and account configuration. No provider speed claim substitutes for these observations, and no minimum Jev speedup is assumed.

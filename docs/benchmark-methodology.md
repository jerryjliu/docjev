# Benchmark methodology

The harness measures authentic provider calls and preserves each observation. A report is evidence for its declared documents, models, OCR, client/network conditions, and sample count. The small synthetic corpus and a real-document video pilot are separate conditions; neither establishes a general speedup across workloads.

The completed [real-document pilot](../benchmarks/results/real-doc-pilot-20260919/report.md) uses one ten-page BEA release and one 15-page packet, three timed repeats, and one excluded warmup per engine/task. Both matched 1/1 declared sources. Jev median decision times were 182.5 ms for classification and 293.8 ms for splitting; Luna's were 785.4 ms and 1,590.8 ms. Repeated Luna input was almost entirely served from its input cache and cost less in the measured portion. The full synthetic evaluation remains unrun.

## Running and regenerating

```sh
uv run python -m benchmarks.run --config benchmarks/configs/default.yaml --dry-run
uv run python -m benchmarks.run --config benchmarks/configs/default.yaml --output benchmarks/results/my-run
uv run python -m benchmarks.report benchmarks/results/my-run
```

`--dry-run` validates source-file hashes and reports planned calls and an estimated budget reservation without remote calls. Execution needs TypeSafe and OpenAI credentials in the environment. Use a new output directory for each run; existing data is never overwritten. `--limit 1 --repeats 3` creates an explicitly labeled small pilot. `--scope end-to-end` measures new OCR from raw files. `--concurrency 4` is a separate mixed-provider throughput condition; the default sequential condition remains primary.

To reproduce the real-document condition, use `--config benchmarks/configs/real-doc-pilot.yaml` and a new output directory. It reserves a maximum estimated $2 locally and declares `demo_set: real`, `experiment_kind: demonstration`, and `warmup_policy: reuse-demo-sources`. Those warmups intentionally reuse the demo inputs; they are not a held-out evaluation.

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

Bootstrap intervals resample whole source documents or packets. Repeats do not change the quality denominator. Reports record repeated-output disagreement, first-pass failed/incorrect IDs, and per-class confusion matrices so correctness accompanies latency.

Costs use reported token/credit counts and `benchmarks/pricing.json`. Provider input-cache reads/writes are distinguished where available. Unknown usage remains unknown; known-cost totals are lower bounds when any charge is unknown. OCR preparation, measured inference, and excluded warmup costs have separate provenance. The run budget includes warmups and optional paid OCR, while the headline measured inference table excludes warmups.

A $10 default local guard reserves an estimated conservative allowance before paid dispatch, retains reserves for unknown charges, and counts concurrent reservations. It is not a guaranteed provider billing cap: token estimates, dynamic window recovery, and delayed billing are imperfect. The dry-run assumption is 12,000 normalized OCR bytes per page; actual dispatch uses observed text sizes for the baseline. Review and add a current price/reservation entry before using a different baseline. Infrastructure costs and account-specific discounts are excluded.

## Artifacts and reproducibility

Each dispatch immediately appends a sanitized `raw.jsonl` observation and flushes it. `manifest.json` records configuration, environment, input identity, and budget progress. `summary.json`, `metrics.csv`, `report.md`, and a branded `latency.svg` regenerate entirely from recorded observations with no API calls. An interrupted run is marked incomplete; frozen missing sources remain in quality denominators. Request IDs and numeric telemetry are retained; API keys and raw provider exception bodies are excluded.

Public model latency varies with document length, question count, provider load, client location, network, and account configuration. No provider speed claim substitutes for these observations, and no minimum Jev speedup is assumed.

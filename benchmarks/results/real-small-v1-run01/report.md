# Real-document accuracy pilot

Run: `real-small-v1-run01`. Recorded 2026-09-19T17:58:58.512745+00:00.

Status: **complete**. Stop reason: `null`.

This is a curated convenience sample of complete, short English public-sector PDFs. The 40 authentic originals are scored individually for classification and reused exactly once across eight constructed packets. These are 40 unique sources and 48 task inputs; task results are separate and must not be pooled. Shared originals and issuer/template families create dependence. Annotation is agent-assisted; human review was not performed. The first measured pass determines quality. Failures, preparation errors, skipped work, and missing results remain unsuccessful in the frozen denominator. Classification changes by 2.5 percentage points per error; packet exact match changes by 12.5 points. Inferential intervals are omitted for this non-random sample. Latency quantiles are descriptive. This does not establish general production accuracy, scan/Office performance, or accuracy on naturally aggregated packets.

| Task | Engine / model | Quality | Completed | Decision p50 / p95 | Samples | Known measured decision API cost |
|---|---|---:|---:|---:|---:|---:|
| classify | jev / jev-1.13.0 | 40/40 correct (100.0%) | 40/40 | 138.6 / 184.5 ms | 40 | $0.005028 (0 unknown-cost calls) |
| classify | openai / gpt-5.6-luna | 40/40 correct (100.0%) | 40/40 | 794.3 / 1208.8 ms | 40 | $0.024406 (0 unknown-cost calls) |
| split | jev / jev-1.13.0 | 7/8 exact (87.5%) | 8/8 | 209.6 / 290.0 ms | 8 | $0.006635 (0 unknown-cost calls) |
| split | openai / gpt-5.6-luna | 8/8 exact (100.0%) | 8/8 | 1352.3 / 1862.7 ms | 8 | $0.022488 (0 unknown-cost calls) |

## Completion and failures

Latency includes only successful complete invocations. Missing values are unavailable, never zero latency.

| Task / engine | Planned | Dispatched | Successful | Failed / invalid | Skipped | Missing terminal |
|---|---:|---:|---:|---:|---:|---:|
| classify / jev | 40 | 40 | 40 | 0 | 0 | 0 |
| classify / openai | 40 | 40 | 40 | 0 | 0 | 0 |
| split / jev | 8 | 8 | 8 | 0 | 0 | 0 |
| split / openai | 8 | 8 | 8 | 0 | 0 | 0 |

Unclosed or contradictory dispatches: 0. Their usage may be unknown; provider-request counts are incomplete when indicated. A start event does not establish that the provider stopped processing or charging.

## OCR, warmups, and measured work

Configured warmups per engine/task: 1. Actual warmup invocations dispatched: 4; terminal records: 4; successful: 4.

Preparation: 50 task-input artifacts, 50 successful, 0 failed/skipped, 2 cache hits. Each preparation is counted once across engines. Cached preparation is not a cold OCR measurement.

| Component | Recorded wall time | Known estimated API cost | Unknown-cost observations |
|---|---:|---:|---:|
| OCR preparation | 55821.3 ms (50 timed inputs) | $0.000000 | 0 |
| Excluded warmup decisions | 4917.9 ms | $0.009494 | 0 |
| Measured decisions | 52090.0 ms | $0.058556 | 0 |

Known preparation conversion: 169.7 ms; OCR: 41376.7 ms. These stage sums are separate from decision latency. LiteParse API cost is zero; local compute cost is not estimated.

Full-run known estimated API cost: **$0.068050**, including warmups and OCR. Unknown-cost observations: 0. Infrastructure costs and account discounts are excluded.

## Scope and settings

- Scope: `decision`. Concurrency: 1. Repeats: 1.
- Decision-only comparisons share exactly the same normalized OCR artifact. Their task wall time excludes OCR. End-to-end scope reports fresh OCR plus decisions in task wall time separately.
- The LLM baseline returns whole-packet segments efficiently in one call when supported. Jev uses page category/boundary questions and bounded windows. This is a practical task comparison; no matched-decision comparison is claimed.
- SDK retries are disabled. Provider caching and network variability are uncontrolled; cached-input/write tokens are reported separately. Separate process-cold startup is not measured.
- The local $2 reservation guard is an estimate, not a provider billing cap. Recorded retained unknown-cost reservations: $0.000000. Separately, unclosed-start reservations are $0.000000; these may overlap the recorded guard balance.
- Price snapshot: 2026-09-18. USD figures use list-price estimates and reported usage; unknown usage stays unknown.

## Quality details

### classify / jev

Macro-F1: 1.0000. Correct: 40/40.

| Category | Support | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| financial_report | 8 | 1.0000 | 1.0000 | 1.0000 |
| legal_notice | 8 | 1.0000 | 1.0000 | 1.0000 |
| other | 8 | 1.0000 | 1.0000 | 1.0000 |
| press_release | 8 | 1.0000 | 1.0000 | 1.0000 |
| tax_form | 8 | 1.0000 | 1.0000 | 1.0000 |

Successful task-wall p50 / p95: 138.9 / 184.8 ms, n=40.
Reported measured decision input: 119,717 tokens, including 0 cached-input tokens and 0 cache-write tokens. Provider caches can materially change costs.
Reported decision requests: 40 (complete). Failed or incorrect first-pass IDs: none. Repeated-run disagreement: not measured (one pass). Error types: `{}`. Skip reasons: `{}`.

### classify / openai

Macro-F1: 1.0000. Correct: 40/40.

| Category | Support | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| financial_report | 8 | 1.0000 | 1.0000 | 1.0000 |
| legal_notice | 8 | 1.0000 | 1.0000 | 1.0000 |
| other | 8 | 1.0000 | 1.0000 | 1.0000 |
| press_release | 8 | 1.0000 | 1.0000 | 1.0000 |
| tax_form | 8 | 1.0000 | 1.0000 | 1.0000 |

Successful task-wall p50 / p95: 794.5 / 1209.0 ms, n=40.
Reported measured decision input: 97,165 tokens, including 0 cached-input tokens and 86,213 cache-write tokens. Provider caches can materially change costs.
Reported decision requests: 40 (complete). Failed or incorrect first-pass IDs: none. Repeated-run disagreement: not measured (one pass). Error types: `{}`. Skip reasons: `{}`.

### split / jev

Exact packets: 7/8; valid coverage: 8/8. Page accuracy: 1.0000 (116/116); page macro-F1: 1.0000. Page metrics weight longer originals more heavily.

Boundary precision / recall / F1: 0.9697 / 1.0000 / 0.9846; matches 32, predicted 33, actual 32.

Segment precision / recall / F1: 0.9512 / 0.9750 / 0.9630; matches 39, predicted 41, actual 40.

Same-category boundary recall: 1.0000 (4/4).


Successful task-wall p50 / p95: 210.2 / 290.3 ms, n=8.
Reported measured decision input: 157,965 tokens, including 0 cached-input tokens and 0 cache-write tokens. Provider caches can materially change costs.
Reported decision requests: 8 (complete). Failed or incorrect first-pass IDs: p001. Repeated-run disagreement: not measured (one pass). Error types: `{}`. Skip reasons: `{}`.

### split / openai

Exact packets: 8/8; valid coverage: 8/8. Page accuracy: 1.0000 (116/116); page macro-F1: 1.0000. Page metrics weight longer originals more heavily.

Boundary precision / recall / F1: 1.0000 / 1.0000 / 1.0000; matches 32, predicted 32, actual 32.

Segment precision / recall / F1: 1.0000 / 1.0000 / 1.0000; matches 40, predicted 40, actual 40.

Same-category boundary recall: 1.0000 (4/4).


Successful task-wall p50 / p95: 1352.6 / 1863.4 ms, n=8.
Reported measured decision input: 87,037 tokens, including 0 cached-input tokens and 87,013 cache-write tokens. Provider caches can materially change costs.
Reported decision requests: 8 (complete). Failed or incorrect first-pass IDs: none. Repeated-run disagreement: not measured (one pass). Error types: `{}`. Skip reasons: `{}`.

Full confusion matrices, frozen denominators, ledgers, and per-item results are in `summary.json`, `metrics.csv`, `raw.jsonl`, and `manifest.json`. Where present, `events.jsonl` preserves dispatch starts and the preparation receipt preserves input identity. Reports regenerate offline from these records.

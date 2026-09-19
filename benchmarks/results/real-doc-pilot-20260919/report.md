# Real-document timing pilot

Run: `real-doc-pilot-20260919`. Recorded 2026-09-19T07:48:51.494562+00:00.

This is a real-document demonstration timing pilot, using one original document and one assembled packet of originals. Three timed repetitions do not establish general speed or held-out accuracy. Source reuse for excluded warmups is intentional and recorded. Quality below means agreement with the declared demo label/assembly on the first timed run. Failures count as unsuccessful. Missing pages count against page recall. Warmups are excluded from this table.

| Task | Engine / model | Quality | Completed | Decision p50 / p95 | Samples | Known decision API cost |
|---|---|---:|---:|---:|---:|---:|
| classify | jev / jev-1.13.0 | 1/1 source matches | 1/1 | 182.5 / 184.1 ms | 3 | $0.001921 (0 unknown-cost calls) |
| classify | openai / gpt-5.6-luna | 1/1 source matches | 1/1 | 785.4 / 1338.0 ms | 3 | $0.000839 (0 unknown-cost calls) |
| split | jev / jev-1.13.0 | 1/1 source matches | 1/1 | 293.8 / 336.7 ms | 3 | $0.003430 (0 unknown-cost calls) |
| split | openai / gpt-5.6-luna | 1/1 source matches | 1/1 | 1590.8 / 1604.4 ms | 3 | $0.001270 (0 unknown-cost calls) |

## Scope and settings

- Scope: `decision`. Concurrency: 1. Repeats: 3. Warmups per engine/task: 1.
- Decision-only comparisons share exactly the same normalized OCR artifact. Their wall time measures only the task call; OCR is excluded. End-to-end scope starts from raw documents with local and remote OCR cache disabled and reports measured wall time separately.
- The LLM baseline returns whole-packet segments efficiently in one call when supported. Jev uses page category/boundary questions and bounded windows. This is a practical task comparison; no matched-decision comparison is claimed.
- SDK retries are disabled; request counts include all reported attempts. Provider cache state and network variability are not controlled. Separate process-cold startup is not measured by this run.
- USD figures use versioned list prices and reported tokens/credits. Unknown usage stays unknown; the local $2 reservation guard is an estimate, not a provider billing cap.
- Bootstrap intervals resample unique sources, not repetitions. A one-source demonstration has no meaningful uncertainty estimate or general accuracy claim. Small-corpus results do not establish production accuracy or latency across deployments.

## Quality details

### classify / jev

Macro-F1: 1.0000. Accuracy bootstrap 95% interval: not estimable with fewer than two unique sources.

Reported measured decision input: 45,735 tokens, including 0 cached-input tokens and 0 cache-write tokens. Provider caches can materially change this repeated-input cost comparison.

Failed or incorrect first-pass IDs: none. Repeated-run disagreement: 0 source(s). Error types: `{}`.

### classify / openai

Macro-F1: 1.0000. Accuracy bootstrap 95% interval: not estimable with fewer than two unique sources.

Reported measured decision input: 39,348 tokens, including 39,339 cached-input tokens and 0 cache-write tokens. Provider caches can materially change this repeated-input cost comparison.

Failed or incorrect first-pass IDs: none. Repeated-run disagreement: 0 source(s). Error types: `{}`.

### split / jev

Page accuracy: 1.0000; page macro-F1: 1.0000. Boundary F1: 1.0000; exact category+range segment F1: 1.0000. Same-category boundary recall: 1.0000. Packet exact-match bootstrap 95% interval: not estimable with fewer than two unique packets.

Reported measured decision input: 81,672 tokens, including 0 cached-input tokens and 0 cache-write tokens. Provider caches can materially change this repeated-input cost comparison.

Failed or incorrect first-pass IDs: none. Repeated-run disagreement: 0 source(s). Error types: `{}`.

### split / openai

Page accuracy: 1.0000; page macro-F1: 1.0000. Boundary F1: 1.0000; exact category+range segment F1: 1.0000. Same-category boundary recall: 1.0000. Packet exact-match bootstrap 95% interval: not estimable with fewer than two unique packets.

Reported measured decision input: 51,903 tokens, including 51,894 cached-input tokens and 0 cache-write tokens. Provider caches can materially change this repeated-input cost comparison.

Failed or incorrect first-pass IDs: none. Repeated-run disagreement: 0 source(s). Error types: `{}`.

Full per-class confusion matrices, first-pass denominators, and request/cost details are in `summary.json`, `metrics.csv`, `raw.jsonl`, and `manifest.json`. The manifest freezes input hashes, prompt-source hashes, parser settings, and machine/package versions.

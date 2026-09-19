# Small real-document evaluation corpus

[v1 dataset card](v1/DATASET_CARD.md) describes the frozen 40-original / eight-packet pilot: 116 unique source pages, five classes with eight originals each, and four excluded warmup calls from existing demo inputs.

The source publications are authentic. Packet combinations are constructed from unchanged complete source pages. Labels were proposed by one agent and independently checked by a separate agent; human review was not performed. [Source provenance and rights](v1/SOURCE.json), [notices](v1/NOTICE.md), [annotations](v1/annotations.json), and [packet boundaries](v1/packet-plan.json) are public evaluation evidence.

The entire v1 directory is immutable after freeze. As a small adjustment to the implementation plan's proposed post-run dataset-card update, actual run links and status belong in this README, outside v1. This prevents reporting updates from invalidating corpus and preparation identities. The v1 dataset card itself makes no accuracy claim.

```sh
uv run python datasets/real-small/prepare.py --verify
uv run python datasets/real-small/prepare.py --verify --render
```

Both commands are offline and read-only. They take source bytes as given, verify frozen hashes and complete page provenance, and never download or repair data. `verify_corpus(repository_root, require_review=True, render=False)` is also callable by the benchmark preparation stage.

The acquisition/review contact sheets and full-page renders under `qa/` are local ignored inspection artifacts. Authoritative release data is in v1. No paid inference is performed by the corpus preparation tool.

## Recorded result

The [single-pass run](../../benchmarks/results/real-small-v1-run01/report.md) completed all 96 measured tasks and four warmups. Jev and GPT-5.6 Luna both classified 40/40 originals correctly. Jev split 7/8 packets exactly; Luna split 8/8. Jev introduced one extra boundary before the Federal Reserve release’s implementation attachment; [the review](../../benchmarks/results/real-small-v1-run01/error-analysis.md) preserves that first-pass error and the original labels.

The total estimated API cost was $0.068050, including warmups; the paid stage took 58.1 seconds after 56.6 seconds of local preparation. These are sample-specific descriptive results, not a production accuracy estimate. The frozen v1 files remain unchanged.

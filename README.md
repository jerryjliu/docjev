# DocJev

**Document classification and splitting with Jev, LiteParse, and optional LlamaParse.**

Give the Python library, CLI, or local app a PDF, DOCX, or PPTX and natural-language category rules. LiteParse extracts complete page text locally; Jev predicts the document category or the boundaries between its component documents. Optional LlamaParse tiers provide cloud OCR for difficult inputs.

The real-document demo uses original IRS, Treasury, BEA, and SEC publications. Its 15-page packet contains two adjacent Treasury auction results with the same category. The splitter identifies them as separate documents and keeps a ten-page BEA release—including its dense statistical tables—together.

- **Classify:** one document → one category, probabilities, and review flags.
- **Split:** one packet → ordered categories and page ranges, with optional per-document PDF export.
- **Measure:** separate OCR and decision timing, provider usage, and a small-LLM comparison.

This is an independent open-source implementation. It does not call LlamaIndex's hosted Classify or Split APIs or use their implementation. LlamaParse is used only for optional OCR. Jev is a hosted service; local OCR does not make inference offline.

[![DocJev visual benchmark report: 40 real PDFs, eight packets, Jev and Luna accuracy and decision latency](docs/report/summary.png)](https://jerryjliu.github.io/docjev/)

**[Explore the visual report](https://jerryjliu.github.io/docjev/)** — browse all 40 documents, compare packet boundaries, replay recorded median timings, and inspect the one extra split.

## Quick start

Requires Python 3.11+ and a [TypeSafe API key](https://console.typesafe.ai/). Clone [DocJev](https://github.com/jerryjliu/docjev) and install it:

```sh
git clone https://github.com/jerryjliu/docjev.git
cd docjev
uv sync
uv run docjev doctor --smoke
```

The package and primary CLI are named `docjev`; `jev-docs` remains a compatibility alias. Python imports (`jev_docs`), environment variables (`JEV_DOCS_*`), and the `.jev-docs/` cache retain their existing names.

Export `TYPESAFE_API_KEY` in your shell before running a Jev decision. [`.env.example`](.env.example) lists the supported environment variables with deliberately empty values; the CLI does not automatically load `.env` files. `LLAMA_CLOUD_API_KEY`, `OPENAI_API_KEY`, and `OPENROUTER_API_KEY` are optional, for cloud OCR, the baseline, and [running Jev through OpenRouter](#jev-through-openrouter) respectively. Keep actual values outside version control and recordings.

```sh
# Classify an original ten-page BEA release.
uv run docjev classify examples/real/originals/r04.pdf \
  --rules examples/real/classify/rules.yaml

# Classify the complete five-document public-finance inbox; output is JSONL.
uv run docjev classify examples/real/originals \
  --rules examples/real/classify/rules.yaml \
  --output output/real-inbox.jsonl

# Split the assembled packet and export each original publication.
uv run docjev split examples/real/public-finance-packet.pdf \
  --rules examples/real/split/rules.yaml \
  --export-dir output/real-segments \
  --output output/real-split.json
```

Output files are preserved by default; use `--overwrite` explicitly to replace them. Results go to stdout and progress/errors to stderr. Directory classification writes one success/error record per supported file and returns a nonzero exit status if any file fails.

DOCX and PPTX require [LibreOffice](https://www.libreoffice.org/). Their page numbers refer to a retained PDF rendering: DOCX pagination follows that rendering and PPTX uses one page per slide. Native PDF input does not need LibreOffice. The first scanned LiteParse parse may download English OCR language data; `doctor --smoke` checks a raster-only PDF. See [compatibility and page contracts](docs/compatibility.md).

## Local visual app and videos

```sh
uv sync --extra demo --extra baseline
uv run docjev demo
```

Open [localhost:8765](http://127.0.0.1:8765). The app defaults to **Original public documents**, with editable categories, source previews, live classification/splitting, and PDF downloads. To load the separate synthetic fixtures, start it with `JEV_DOCS_DEMO_SET=synthetic uv run docjev demo`. The comparison panel explicitly labels saved pilot results and their sample size; keys stay on the local server.

For a live side-by-side comparison, open [localhost:8765/race](http://127.0.0.1:8765/race). It prepares LiteParse text once, then launches Jev and GPT-5.6 Luna together when you click **Run both models**. Both API keys are required for this comparison. The model decision times exclude OCR, which is displayed separately. Each preparation permits one comparison; rules can be edited before launch.

**Short social demos:** [Classification](docs/media/social/classification.mp4) · [Splitting](docs/media/social/splitting.mp4). Both open directly on the app, with the run click in the first second, larger original pages, and live model results side by side. [Thumbnails, captions, exact timings, and run evidence](docs/media/social/README.md) are included.

Longer walkthroughs: [Publication inbox](docs/media/classification.mp4) · [15-page packet](docs/media/splitting.mp4). All videos are captioned, silent 1080p screen recordings; retained processing plays at normal speed. The [actual split PDFs and result JSON](docs/media/split-output.zip) are from the longer walkthrough. See [publishing notes](docs/publishing.md) to share the prepared repository and video assets.

**Accuracy results:** The separate [40-document accuracy pilot](benchmarks/results/real-small-v1-run01/report.md) is complete. Both engines classified 40/40 originals correctly; Jev split 7/8 packets exactly and Luna split 8/8. The video demonstrations remain separate evidence.

The [next 40-document challenge](datasets/real-challenge/README.md) targets scans, ambiguous categories, and attachment boundaries. It is a preparation protocol, not another measured result.

## Rules and results

Rules use stable category IDs and descriptions of document purpose:

```yaml
categories:
  - id: invoice
    description: A seller's request for payment for goods or services already supplied.
  - id: purchase_order
    description: A buyer's authorization to supply goods or services.
  - id: other
    description: Content that does not fit the defined categories.
instructions: Classify the whole document by its main purpose.
splitting_instructions: Keep continuation pages together. Different invoice references identify separate documents, even when adjacent documents share a category.
```

`other` is added automatically if omitted. The real demo's [classification rules](examples/real/classify/rules.yaml) distinguish tax forms, transaction-specific financial reports, narrative press releases, and legal notices. Its [splitting rules](examples/real/split/rules.yaml) distinguish new publications from sections, vouchers, tables, and technical notes within a publication.

The measured packet produces these four segments, with one-based page numbers:

```json
{
  "segments": [
    {"id": "segment-001", "category": "tax_form", "pages": [1, 2, 3]},
    {"id": "segment-002", "category": "financial_report", "pages": [4]},
    {"id": "segment-003", "category": "financial_report", "pages": [5]},
    {"id": "segment-004", "category": "press_release", "pages": [6, 7, 8, 9, 10, 11, 12, 13, 14, 15]}
  ]
}
```

This excerpt omits provenance, page decisions, review flags, and metrics from the full result. Every successful split covers every canonical page exactly once. Empty OCR is accepted as a blank page only after a conservative visual check; visibly nonblank pages with unreadable text fail explicitly. Exports verify the canonical PDF hash and preserve exact page membership.

Segments include structured `review_reasons` with page numbers. By default, a Jev boundary score within 0.1 of the decision threshold triggers review of either a cut or a continuation; an uncertain cut flags both adjacent segments. Use `--boundary-review-margin 0` to disable this signal. It does not change page ranges, does not flag deterministic blank-page boundaries, and does not invent boundary scores for the baseline. Category uncertainty, `other`, and category/boundary conflicts remain separate reasons. See [boundary review](docs/boundary-review.md).

Jev's selected-category probability and provider confidence are different values. Neither is claimed to be calibrated. A segment's mean category probability is an average of page scores, not a joint probability. Jev supplies decisions and distributions, so the package does not invent explanatory rationales.

## Python API

```python
from jev_docs import classify_document, load_rules, parse_document, split_document
from jev_docs.export import export_segments

classification = classify_document(
    "examples/real/originals/r04.pdf",
    load_rules("examples/real/classify/rules.yaml"),
)
print(classification.category)

document = parse_document("examples/real/public-finance-packet.pdf")
splitting = split_document(document, load_rules("examples/real/split/rules.yaml"))
export_segments(document, splitting, "output/python-segments")
print(splitting.model_dump_json(indent=2))
```

`aclassify_document` and `asplit_document` support async applications. Passing a previously parsed document reuses its page text. Library results carry its parse provenance and metrics forward; use `metrics.decision_ms` for inference latency. The benchmark explicitly resets historical OCR time/cost for decision-only measurements.

## OCR options

| OCR | CLI selection | Where parsing runs |
|---|---|---|
| LiteParse, default | `--ocr liteparse` | Local native Python parser with OCR enabled |
| LlamaParse Cost Effective | `--ocr llamaparse --tier cost-effective` | LlamaParse Parse v2 |
| LlamaParse Agentic | `--ocr llamaparse --tier agentic` | LlamaParse Parse v2 |
| LlamaParse Agentic Plus | `--ocr llamaparse --tier agentic-plus` | LlamaParse Parse v2 |

```sh
uv sync --extra llamaparse

# Requires LLAMA_CLOUD_API_KEY as well as TYPESAFE_API_KEY.
uv run docjev classify examples/real/originals/r04.pdf \
  --rules examples/real/classify/rules.yaml \
  --ocr llamaparse --tier agentic-plus

# Inspect OCR without making a decision-engine call.
uv run docjev parse examples/real/originals/r04.pdf --output output/pages.json
```

Use `--parser-version` to pin a valid tier-specific published LlamaParse version. The default is `latest`; unresolved versions are reported explicitly and local `latest` cache entries expire after 24 hours. `--no-cache` bypasses local OCR reuse and disables LlamaParse server cache. Canonical PDFs remain available for previews and export. The local `.jev-docs/` cache contains extracted text and document bytes and is ignored by Git.

PDF bytes are uploaded only when LlamaParse is selected. Normalized page text is sent to the selected decision engine—TypeSafe by default, OpenRouter when `--engine openrouter` is selected, or OpenAI for the optional baseline. LiteParse has no OCR API fee; compute resources and hosted decision calls still have costs.

## Jev through OpenRouter

[OpenRouter](https://openrouter.ai/~typesafe/jev-latest) serves Jev through its [Decisions API](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request). The `openrouter` engine sends the same page state and questions as the direct engine, with the same windowing, retry, and context-recovery behavior.

```sh
uv sync --extra openrouter

# Requires OPENROUTER_API_KEY instead of TYPESAFE_API_KEY.
uv run docjev classify examples/real/originals/r04.pdf \
  --rules examples/real/classify/rules.yaml \
  --engine openrouter

# Track the newest Jev release instead of the pinned default.
uv run docjev split examples/real/public-finance-packet.pdf \
  --rules examples/real/split/rules.yaml \
  --engine openrouter --model '~typesafe/jev-latest'
```

The default model is `typesafe/jev-1.13`. Request records report OpenRouter's billed `usage.cost` as `cost_status: reported`, rather than a list-price estimate. Published benchmark results were measured against TypeSafe directly and are not re-run for this engine.

## Small real-document accuracy benchmark

**40 authentic PDFs, eight per category, reused across eight constructed five-document packets.** This curated English public-sector sample contains 116 unique pages. The [frozen dataset](datasets/real-small/v1/DATASET_CARD.md) includes complete original publications, source-specific rights, agent-reviewed labels, and verified packet boundaries. Human annotation review was not performed.

One measured pass completed all 96 tasks, plus four excluded warmups. Both engines received the same LiteParse text. Decision times exclude OCR; concurrency was one and retries were disabled.

| Task | Jev 1.13.0 quality | GPT-5.6 Luna quality | Jev median | Luna median | Luna/Jev median-time ratio |
|---|---:|---:|---:|---:|---:|
| Classification | 40/40 correct | 40/40 correct | 138.6 ms | 794.3 ms | 5.73× |
| Splitting | 7/8 exact packets | 8/8 exact packets | 209.6 ms | 1,352.3 ms | 6.45× |

Timing ratios use the same 40 completed classification inputs and eight completed splitting inputs for each engine. Both found all 32 true packet boundaries, including all four adjacent same-category boundaries, and labeled all 116 packet pages correctly. Jev added one extra boundary before a Federal Reserve statement’s implementation attachment; the frozen rules treat it as part of the original publication. See the [error review](benchmarks/results/real-small-v1-run01/error-analysis.md).

Measured decisions cost an estimated **$0.011663 for Jev** and **$0.046894 for Luna**. The entire run, including warmups, cost **$0.068050**, with all provider usage recorded. Local preparation took 56.6 seconds; the paid stage took 58.1 seconds. LiteParse has no API fee; local compute is not priced. Two warmup inputs used cached OCR, so preparation is not wholly cold.

These are descriptive results on a small convenience sample, with shared source/template families and uncontrolled provider caching. The tasks reuse the same originals and are reported separately. Eight packets do not establish general splitting accuracy; no inferential confidence interval or repeat-stability claim is made.

[Full report](benchmarks/results/real-small-v1-run01/report.md) · [Raw results](benchmarks/results/real-small-v1-run01/raw.jsonl) · [Metrics CSV](benchmarks/results/real-small-v1-run01/metrics.csv) · [Frozen run manifest](benchmarks/results/real-small-v1-run01/manifest.json) · [Dataset and notices](datasets/real-small/README.md) · [Methodology](docs/benchmark-methodology.md)

![Accuracy-pilot decision latency](benchmarks/results/real-small-v1-run01/latency.svg)

To run your own single-pass comparison:

```sh
uv sync --all-extras --locked
uv run python datasets/real-small/prepare.py --verify
uv run python -m benchmarks.run --config benchmarks/configs/real-small-v1.yaml --dry-run

# Local OCR and actual-text admission only; no inference calls.
uv run python -m benchmarks.run --config benchmarks/configs/real-small-v1.yaml \
  --prepare-only --output output/my-real-small-preflight

# Requires TYPESAFE_API_KEY and OPENAI_API_KEY; consumes this receipt once.
uv run python -m benchmarks.run --config benchmarks/configs/real-small-v1.yaml \
  --prepared output/my-real-small-preflight/preparation.json \
  --output benchmarks/results/my-real-small-run

# Rebuild saved results offline, without keys.
uv run python -m benchmarks.report benchmarks/results/my-real-small-run
```

The profile enforces a $2 local estimated guard, 60-second OCR/task limits, a 600-second preparation limit, and a 300-second paid-stage limit. It stops on service failures and preserves incomplete outcomes in the original denominator. The guard is not a provider billing cap; a preparation receipt cannot be reused for another paid attempt.

## Earlier real-document timing pilot

**Three timed repeats of one ten-page BEA document and one 15-page packet, per engine. This is a demonstration timing pilot, not a held-out accuracy benchmark.** One excluded warmup preceded each engine/task condition. Both engines consumed the same LiteParse page text, with reused clients, sequential execution, and no retries. OCR is excluded from these decision times.

| Task | Jev 1.13.0 median | GPT-5.6 Luna median | Luna/Jev median-time ratio | Correct demo source |
|---|---:|---:|---:|---:|
| Classify BEA release, 10 pages | 182.5 ms | 785.4 ms | 4.30× | Both: 1/1 |
| Split public-finance packet, 15 pages | 293.8 ms | 1,590.8 ms | 5.41× | Both: 1/1 |

Both engines reproduced the declared category and all four packet segments on all three timed repeats, including the boundary between adjacent Treasury results. All 16 task calls, including warmups, completed. The full pilot's estimated API cost was **$0.01694**, calculated from reported usage and list prices.

Luna's timed calls benefited from near-complete repeated-input caching and cost less here: measured inference totaled $0.002109 for Luna versus $0.005351 for Jev across six timed calls each. Provider cache state was not controlled. These measurements establish neither a general speedup nor a general cost advantage; network, input length, question count, and provider load matter. Three timing samples also provide only a rough p95, and one source cannot support a meaningful accuracy confidence interval.

[Full report](benchmarks/results/real-doc-pilot-20260919/report.md) · [Raw observations](benchmarks/results/real-doc-pilot-20260919/raw.jsonl) · [Frozen manifest](benchmarks/results/real-doc-pilot-20260919/manifest.json) · [Metrics CSV](benchmarks/results/real-doc-pilot-20260919/metrics.csv) · [Methodology](docs/benchmark-methodology.md)

![Measured real-document decision latency](benchmarks/results/real-doc-pilot-20260919/latency.svg)

Reproduce this condition with your own keys; paid execution is explicit:

```sh
uv sync --extra baseline
uv run python -m benchmarks.run --config benchmarks/configs/real-doc-pilot.yaml --dry-run
uv run python -m benchmarks.run --config benchmarks/configs/real-doc-pilot.yaml \
  --output benchmarks/results/my-real-doc-pilot

# Regenerate tables and charts from recorded observations, without API calls.
uv run python -m benchmarks.report benchmarks/results/my-real-doc-pilot
```

The pilot has a $2 estimated local reservation guard. It is not a provider billing cap. Unknown usage is preserved as unknown, and the run stops dispatching work that cannot fit the remaining estimated allowance.

## Sources and evaluation data

The real collection contains exact original downloads from the [IRS](https://www.irs.gov/pub/irs-pdf/f941.pdf), [Treasury](https://fiscaldata.treasury.gov/static-data/published-reports/auctions-query/results/R_20250812_1.pdf), [BEA](https://www.bea.gov/sites/default/files/2025-08/pi0725.pdf), and [SEC / Office of the Federal Register](https://public-inspection.federalregister.gov/2025-11513.pdf). The packet was assembled for this independent demo and was not issued by those agencies. All 15 packet pages were verified against their original rendered pages. See [source descriptions and reuse terms](examples/real/README.md) and [exact download hashes](examples/real/SOURCE.json). Source dates and statistics are historical publications, not current financial guidance; no agency endorsement is implied.

The separate [accuracy corpus](datasets/real-small/README.md) adds 40 original PDFs and eight constructed packets, with [per-source provenance](datasets/real-small/v1/SOURCE.json) and [reuse notices](datasets/real-small/v1/NOTICE.md).

A **separate synthetic corpus** contains 60 classification documents and 24 split packets, with independent development/test source identities, scans, continuation pages, blanks, and adjacent same-category documents. Its generator, labels, and [dataset card](datasets/DATASET_CARD.md) are included for broader evaluation. The full synthetic benchmark has **not been run**; no synthetic accuracy result is claimed.

```sh
uv sync --all-extras
uv run python datasets/generate.py --verify
uv run python examples/real/assemble.py --verify
uv run python -m benchmarks.run --config benchmarks/configs/default.yaml --dry-run
```

The default full evaluation plans 48 classification test sources and 18 test packets, five repeats, three development warmups per engine/task, and a $10 estimated reservation guard. Add `--scope end-to-end` for separately measured raw-document pipeline runs. Keep conditions separate in published results.

## Development and limitations

```sh
uv sync --all-extras
uv run ruff check .
uv run mypy src/jev_docs
uv run pytest
uv build
```

Default tests make no paid provider calls. The three optional LlamaParse tier checks require `JEV_DOCS_LIVE_OCR=1`; details are in [compatibility](docs/compatibility.md). Office tests require LibreOffice. A source checkout is the supported route for benchmark scripts, saved comparison reports, and datasets; the wheel includes the library, CLI, app assets, and demo inputs.

Splitting is page-level and contiguous. Very large whole-document classification fails explicitly; large packets use context windows, and an oversized individual page/context pair still fails. No text is silently truncated. The app runs on localhost with in-process jobs and is intended for local demonstrations. See [architecture](docs/architecture.md), [limitations](docs/limitations.md), [contributing](CONTRIBUTING.md), and [security](SECURITY.md).

Code is [Apache-2.0](LICENSE). Synthetic documents have a [CC0 dedication](datasets/LICENSE). The real publications retain their [demo-source terms](examples/real/README.md#redistribution-and-attribution) and [accuracy-corpus reuse terms](datasets/real-small/v1/NOTICE.md); official seals and logos retain their protections. LlamaIndex brand assets and bundled font notices are described in [NOTICE](NOTICE).

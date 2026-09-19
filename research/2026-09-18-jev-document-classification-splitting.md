---
date: 2026-09-18T23:15:00-07:00
git_commit: null
branch: null
repository: 2026_09_18_jev_doc_classify_splitting (new workspace, not yet a Git repository)
topic: "Jev document classification and splitting: public APIs, OCR, evaluation, and demo feasibility"
tags: [research, jev, liteparse, llamaparse, classification, splitting, evaluation]
status: complete
last_updated: 2026-09-18
last_updated_by: codex
---

# Research: Jev document classification and splitting

## Research Question

What exists today that can support a publishable open-source Python package and CLI for document classification and page segmentation with Jev, local LiteParse OCR by default, optional LlamaParse tiers, two branded video demonstrations, and measured comparisons against a small LLM?

This document records findings. The companion implementation plan contains proposed architecture, datasets, and delivery choices. No implementation, inference benchmark, or video has been created in this research pass.

## Summary

- The workspace was empty and was not a Git repository. There is no existing application architecture or test suite to preserve.
- Jev provides categorical choices and probabilities against text state, with multiple independent questions in one request. This can express document category, page category, and a boundary before a page. It does not generate free-text explanations.
- LiteParse now has native Python bindings. The installed Python package and CLI are different versions, so reproducing current documentation requires an isolated environment.
- LlamaParse's current Parse v2 SDK exposes all three requested tiers and page-level Markdown. Office pagination needs an explicit rendering contract if results are to identify usable pages.
- The public LlamaParse Classify/Split schemas provide useful shape references. Their implementation was not inspected.
- Published Jev speed claims are vendor results, not measurements on this proposed workload. OCR and whole-packet decision latency must be measured separately.
- The current shell has LlamaCloud/OpenAI credential variables but no `TYPESAFE_API_KEY`. Presence does not verify that a key is valid or that a model is accessible.

## Detailed Findings

### 1. Workspace and execution environment

The initial directory contained no files, including no project configuration, source, tests, datasets, or `AGENTS.md`. Ancestor instruction files were checked; none were found. `git rev-parse` reported no repository. See [workspace inventory](2026-09-18-workspace-inventory.txt), lines 1–6.

The default Python is 3.10.8. `uv`, Node/npm, FFmpeg, a LibreOffice executable, and `lit` are available. The Python environment contains `liteparse==1.0.1`, `llama-cloud==2.1.0`, `llama-parse==0.6.54`, and `openai==1.109.1`; `typesafe-sdk` is absent. The `lit` executable reports 2.0.0. The available LibreOffice reports an alpha build. These are observations, not a tested compatible project environment. Inventory lines 7–20.

Only credential-variable presence was inspected. Values were not printed, copied, or written to artifacts. No remote inference was performed. Inventory lines 21–25.

### 2. Jev's decision interface

The [official introduction](https://docs.typesafe.ai/introduction) describes text state plus typed questions. `Choice` returns a selected option, its distribution, and confidence; `Noul` returns a value between zero and one for a proposition. Questions may share one state and are evaluated independently. One question cannot consume another question's answer in the same call.

The [release article](https://typesafe.ai/blog/introducing-system-one-models-and-jev) is dated September 15, 2026 and describes early access. Its latency/speedup claims come from TypeSafe's own workloads and explicitly discuss favorable input lengths and comparison configurations. They do not establish document-classification or segmentation performance, nor does constrained output establish semantic correctness.

The [Python SDK](https://docs.typesafe.ai/sdk/python) package is `typesafe-sdk`, importing `AsyncTypeSafeClient`, `Choice`, and `Noul` from `typesafe_sdk`. It reads `TYPESAFE_API_KEY`. [Inspected SDK metadata](https://github.com/typesafe-ai/typesafe-sdk-python/blob/2ce5c65f13646cab6e6f782328194c9d85f3300a/pyproject.toml#L1) is version 0.7.0, MIT, Python ≥3.10; the [published release](https://pypi.org/project/typesafe-sdk/0.7.0/) matches. [Model documentation](https://docs.typesafe.ai/models) lists `jev-1.13.0`; the resolved model must be recorded for live results.

Two relevant semantics affect the design:

- [Question dictionary keys](https://docs.typesafe.ai/api) are not model-visible instructions: a question about page 7 must explicitly name page 7 in its instructions. The async call is `client.system_one(state=..., questions=..., model=...)`.
- There is no generated rationale to put in a `reasoning` field. Category probabilities and explicit boundary decisions are the available evidence.
- [Choice confidence](https://docs.typesafe.ai/confidence) is a distribution-derived statistic, distinct from the winning category's probability; Noul has no separate confidence field.

Limits reported in the [model documentation](https://docs.typesafe.ai/models) are 64k total input tokens and 32k for state plus the longest individual question, with up to 255 choice options stated in the release article. Published service rates are 250k tokens/second and 1,200 requests/minute, subject to change. These are bounds to preflight and verify, not throughput guarantees. No official local tokenizer or token-count endpoint was found in the reviewed SDK or [OpenAPI](https://api.typesafe.ai/openapi.json); a local character heuristic cannot prove exact compliance. A separate maximum number of questions was not established.

The current [price](https://docs.typesafe.ai/models) is $0.042 per million input tokens with no output-token fee. [Usage fields](https://github.com/typesafe-ai/typesafe-sdk-python/blob/2ce5c65f13646cab6e6f782328194c9d85f3300a/src/typesafe_sdk/_core/response_types.py#L65) may be nullable. Client wall-clock timing is still necessary; neither vendor speed claims nor response probabilities are latency measurements. The SDK has built-in retries, so instrumentation must account for attempts rather than adding an unmeasured second retry layer.

The [known limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13) include irrelevant state and instructions embedded in document text. These motivate direct questions and error fixtures; they do not imply that a prompt guarantees protection. The official [LLM adapter's discrete mode](https://github.com/typesafe-ai/system-one-adapter-python/blob/adffc2eab300a4fa3c0e92252d4ffd6ceaa53700/src/system_one_adapter/_utils/probability_normalization.py#L95) synthesizes one-hot probabilities, which cannot serve as measured baseline confidence.

### 3. LiteParse: local OCR and page identity

The current [LiteParse overview](https://developers.llamaindex.ai/liteparse/) describes a Rust implementation with native Python support, local text extraction, built-in OCR, and screenshots. [PyPI 2.14.6](https://pypi.org/project/liteparse/2.14.6/) lists Python ≥3.10 and Apache-2.0. The [Python README](https://github.com/run-llama/liteparse/blob/main/packages/python/README.md) documents `from liteparse import LiteParse`, `.parse(path)`, and `.screenshot(path, page_numbers=[...])`.

The [public Python types](https://github.com/run-llama/liteparse/blob/main/packages/python/liteparse/types.py#L159) expose `result.pages`, `total_pages`, `num_pages`, and `page_errors`. Page objects include `page_num`, `text`, `markdown`, dimensions, and text items. Page lookup is 1-based. `total_pages` counts source pages before filtering; `num_pages` counts returned pages. Therefore merely counting returned text objects is insufficient to prove complete processing.

The [CLI JSON serializer](https://github.com/run-llama/liteparse/blob/main/crates/liteparse/src/output/json.rs#L47) uses `pages[].page`, different from the Python binding's `page_num`. The [CLI reference](https://developers.llamaindex.ai/liteparse/cli-reference/) supports `lit parse document.pdf --format json -o output.json`.

[OCR configuration](https://developers.llamaindex.ai/liteparse/guides/ocr/) documents selective OCR and Tesseract language data that is downloaded/cached on first use. Offline readiness therefore includes language data, not just installing a wheel. Local inference has no OCR API charge; machine time and memory still have costs.

[Multi-format support](https://developers.llamaindex.ai/liteparse/guides/multi-format/) documents LibreOffice conversion for Office files and native image conversion. For a DOCX, a page is a rendered PDF page, affected by fonts and the converter. A PPTX page is a rendered slide under the chosen export settings. Independently rendering the same Office file through two providers is not evidence that pagination is identical.

### 4. Optional LlamaParse OCR

The [Parse v2 quickstart](https://developers.llamaindex.ai/llamaparse/parse/getting_started/) uses `llama-cloud`: upload with `purpose="parse"`, then call `client.parsing.parse(file_id=..., tier=..., version=..., expand=["markdown", "usage"])`. The helper handles polling; an async client is available. This is the Parse API, not the Classify or Split service. The current [SDK release](https://pypi.org/project/llama-cloud/2.16.0/) is 2.16.0.

The [tier documentation](https://developers.llamaindex.ai/llamaparse/parse/guides/tiers/) gives exact tier values `cost_effective`, `agentic`, and `agentic_plus`. The version can be a published date or `latest`; reproducible measurements need a resolved or pinned version.

[Results documentation](https://developers.llamaindex.ai/llamaparse/parse/guides/retrieving-results/) exposes `result.markdown.pages` with `page_number`, `markdown`, and `success`. Usage is under `result.job.usage.credits`, potentially null before billing settles. [Configuration documentation](https://developers.llamaindex.ai/llamaparse/parse/guides/configuring-parse/) uses 1-based page ranges and supports `disable_cache=True`. Missing/failed pages must remain visible as errors rather than silently disappearing.

[Published pricing](https://developers.llamaindex.ai/llamaparse/general/pricing/) on the research date is $1.25 per 1,000 credits: 3 credits/page for cost-effective, 10 for agentic, and 45 for agentic plus. The equivalent list prices are $0.00375, $0.0125, and $0.05625 per page. Cache reuse within the documented window can change billed cost. Any calculated figure must be labeled estimated until usage confirms it.

### 5. Public Classify/Split shape references

Only public documentation was read, as requested; no service code, private prompts, or internal implementation was accessed.

The [Classify SDK guide](https://developers.llamaindex.ai/llamaparse/classify/sdk/) shows natural-language rules with `{type, description}` and result fields such as `type`, `confidence`, and `reasoning`. This informs the input/output concept, not a requirement to preserve SDK names or fabricate Jev explanations.

The [Split guide](https://developers.llamaindex.ai/llamaparse/split/getting_started/) shows categories `{name, description}`, optional custom splitting instructions, and `segments[]` with `category`, 1-based `pages`, and `confidence_category`. It documents uncategorized-page policies. Those shapes do not establish an algorithm or calibrated confidence semantics for this new project.

### 6. Small-LLM baseline and measurement constraints

The [GPT-5.6 Luna model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna) positions it for cost-sensitive, high-volume tasks and documents structured output and `reasoning.effort="none"`. Default reasoning is medium. Current list rates are $0.20/$0.02/$1.20 per million ordinary-input/cached-input/output tokens. The fetched page did not identify a dated snapshot, so an invented date-suffixed model name would be unjustified.

The [GPT-4o mini page](https://developers.openai.com/api/docs/models/gpt-4o-mini) provides a historical small-model alternative with a dated snapshot. One small baseline is sufficient for the initial release; broad model rankings would require separate work.

[Structured-output guidance](https://developers.openai.com/api/docs/guides/structured-outputs) documents `client.responses.parse(..., text_format=Schema)`. Refusals and incomplete output require explicit handling. [Prompt-cache documentation](https://developers.openai.com/api/docs/guides/prompt-caching) describes separate cached-input and cache-write accounting, including Luna's 1.25× input cache-write price. A cost calculation cannot simply multiply all input tokens by one rate when these counters are present.

There are no local latency or accuracy measurements yet. Benchmark design must also distinguish category grouping from document-instance segmentation: adjacent documents can share a category, so category changes alone cannot identify all true boundaries. This is a task-definition consequence, not a claim about either model's measured performance.

### 7. Datasets and release assets

No sample documents or labeled dataset existed in the workspace. First-party synthetic documents can provide known source identities and assembly boundaries without relying on model-generated ground truth. The exact proposed collection is specified in the plan.

For optional external validation, the [official DocLayNet repository](https://github.com/DS4SD/DocLayNet) supplies page-level PDFs/images and document metadata across six document categories. It is a layout dataset; adapting it into packets creates a new task. Its [CDLA-Permissive-1.0 license](https://github.com/DS4SD/DocLayNet/blob/main/LICENSE) requires preserving applicable notices and conditions. This pass did not obtain or redistribute any data.

### 8. Brand and recording resources

The [official brand page](https://www.llamaindex.ai/brand) specifies Overused Grotesk for headings/body and IBM Plex Mono for technical labels. Relevant colors are off-white `#F5F5F5`, black `#000000`, gray `#737373`, purple `#3E18F9`, cyan `#37D7FA`, blue `#4B72FE`, pink `#FF8DF2`, and orange `#FF8705`. Official wordmarks and generous surrounding space are preferred. The page links an [official asset archive](https://www.llamaindex.ai/files/llamaindex-brand.zip).

The local recording-skill folder already contains brand assets, font licenses, and provenance. These are planning references, not project dependencies. Any reused deliverable asset needs a portable local copy with its notice; a public repo cannot rely on a path under this user's home directory. The existing screen-recording workflow targets the LlamaParse cloud UI, so its full workflow is not assumed to apply to the new local app.

## Code References

There are no pre-existing project code references. The source of truth for local state is [workspace inventory](2026-09-18-workspace-inventory.txt): lines 1–6 for repository state, 7–20 for tools, 21–25 for credential presence and research scope.

Public OCR source references, inspected without accessing Classify/Split implementation:

- [LiteParse Python bindings README](https://github.com/run-llama/liteparse/blob/main/packages/python/README.md).
- [LiteParse Python page/result types](https://github.com/run-llama/liteparse/blob/main/packages/python/liteparse/types.py#L159).
- [LiteParse CLI JSON serializer](https://github.com/run-llama/liteparse/blob/main/crates/liteparse/src/output/json.rs#L47).

## Architecture Notes

The verified dependency interfaces form a plausible sequence: a file becomes ordered page text through a parser; Jev consumes text state and typed questions; application code converts decisions into categories or page segments. This is a feasibility finding, not an implemented architecture. No existing internal LlamaIndex classifier/splitter is needed to investigate or build that sequence.

## Open Questions

1. Is Jev early access available to the user? A question is pending; no key is present in the current process.
2. Do the pinned current SDKs, native wheels, OCR data, and converter work together on the target platforms? Installation and live smoke tests are deferred to implementation.
3. Which published LlamaParse version is available for all three tiers in the user's account?
4. How reliable is category/boundary prediction on realistic continuation pages, adjacent same-type documents, scans, and unknowns? Only the planned benchmark can answer.
5. What speed, error rate, and API cost will be measured under this network/account configuration? No numerical result is established yet.
6. Repository/package naming and license choice are proposed defaults, not verified name availability or a publishing action.

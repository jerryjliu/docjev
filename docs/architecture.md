# Architecture

The Python library is the single implementation used by the CLI, benchmark harness, and local app.

1. `documents.parse_document` retains a canonical PDF, extracts every page with a selected OCR adapter, verifies coverage, and optionally caches the result.
2. `engines.jev` builds typed category and boundary questions over ordered page text. A whole packet normally fits one request. Larger packets use overlapping context windows with exactly one output owner per page.
3. `classify` maps a whole-document decision to the public classification schema. `split` creates a segment on a category change or source-document boundary, including adjacent same-category documents.
4. `export` copies the exact source pages into per-segment PDFs. Office inputs export their retained canonical PDF pages.
5. `engines.openai` provides a direct, terse structured-output baseline. Its practical splitter returns all segments in one request when supported.
6. `engines.openrouter` sends the same Jev questions through OpenRouter's Decisions API and reuses the `engines.jev` windowing, retries, and answer checks.

No LlamaIndex Classify or Split API is called. The optional LlamaParse adapter only calls file upload and Parse.

Jev Choice confidence and winning-class probability are separate fields. Segment mean probability is only an average of page probabilities, not a calibrated joint probability. The small-LLM baseline emits no confidence value.

Results include client wall-clock stage timings and per-request usage. Network, queueing, and provider processing are part of request latency; these are not isolated GPU inference measurements. Unknown charges remain unknown.

## Pages and context

Public page numbers are one-based. A DOCX page refers to the retained PDF rendering; a PPTX page refers to its rendered slide. Blank pages stay in coverage. Empty OCR text must pass a visual blank check before the page can be called blank.

Jev has separate state-plus-longest-question and complete-request budgets. Local UTF-8 size checks are approximate. A whole classification that is too large fails visibly; splitting can shrink windows, but never truncates individual page text.


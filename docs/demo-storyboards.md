# DocJev: real-document video storyboards

Two actual product walkthroughs, approximately 60–100 seconds each, delivered at 1920×1080 with the recorded pointer. The raw captures are 1670×1080; the final videos crop browser chrome and add branded titles and captions. The videos use original public-sector documents from official sources, not generated forms or fictional business examples. The main scenario is a **public finance and regulatory inbox**: financial reporting, economic releases, and tax documents.

The local app retains the original appearance of every source page. The splitting packet is a concatenation of real pages; the packet assembly is a demonstration, not a claim that the source agencies originally issued those documents together. Source links and any excerpt notes are visible above the preview. The frozen set contains IRS Form 941 (three pages), two Treasury auction result sheets (one page each), a BEA income-and-spending release (ten pages), and a two-page SEC notice. The 15-page splitting packet combines the first four originals. Refer to `examples/real/demo-manifest.json` and `SOURCE.json` for exact provenance.

## Preparation

1. Install the `demo` extra and set credentials through the README's local setup. Keep credential values, terminal history, notifications, and unrelated tabs out of frame.
2. Start `docjev demo`. If `examples/real/demo-manifest.json` is present, the app selects it automatically. `JEV_DOCS_DEMO_SET=real` explicitly requires this set. `JEV_DOCS_PROJECT_DIR` selects an alternate repository/example collection. Restart the server after adding or changing a manifest.
3. For a visually rich classification opening, select **BEA income & spending release** (`r04`). Confirm the input tray says **Original public documents**, sample titles match the published originals, and **View sources** opens the official publisher links. Excerpts must say **Original document excerpt**; the combined packet must say **Packet of original documents**.
4. Rehearse a real classification and split. Check every returned boundary against the original source pages, including neighboring documents of the same category. A failed run remains an error; do not substitute a prediction.
5. Keep the authentic result JSON for each recorded run. Model, parser, timings, cache status, and request records support any captioned numbers.
6. Before recording, dismiss permission alerts and hide recorder control panels from the capture. Make a short pilot recording and inspect it. Fix the camera framing and browser zoom before the final take.

## Planning outline — Film 1: Organize a public finance inbox

This outline was written before recording. The **Actual recorded flow** appendix below describes what appears in the finished videos; proposed wording edits and download interactions must not be treated as footage that was captured.

| Time | Actual interaction | Caption / narrative |
|---|---|---|
| 0–8s | Start on **Classify documents**. Show the original financial report, economic release, and tax document in the sample tray. | “Real documents. Different purposes.” |
| 8–16s | Open **View sources** for a sample and briefly show its official publisher. Keep the document's original page design visible. | “Original documents, from public sources.” |
| 16–27s | Click **Edit rules**. Inspect the financial-report, press-release, tax-form, and legal-notice descriptions. Save a meaningful wording edit. | “Define your categories in plain language.” |
| 27–42s | Select a real document, keep **LiteParse · local OCR**, and click **Classify document**. Keep the decision stage at real speed. | “LiteParse reads the pages. Jev applies your rules.” |
| 42–53s | Inspect the returned category and native category probabilities. Move between the actual source pages where available. | “A category grounded in the document's content.” |
| 53–65s | Select a contrasting original—such as the tax form after an economic release—and run it. | “The same rules, another kind of document.” |
| 65–78s | Frame Read/OCR, Jev decision, and Full pipeline. Open the optional OCR selector if useful. | “Measure reading and decisions separately.” |
| 78–90s | Download **Result JSON**. If a real-document pilot exists, frame its saved comparison and sample counts. | “Structured results, with measured latency.” |

If the recorded input is a report excerpt, say so. Do not describe the provided pages as the complete report. Do not imply that a familiar government form represents difficult OCR unless the observed source warrants that claim.

## Planning outline — Film 2: Recover the documents in a packet

| Time | Actual interaction | Caption / narrative |
|---|---|---|
| 0–9s | Click **Split a packet**. Show the combined public-finance PDF and its provenance disclosure. | “Original public documents, combined into one packet.” |
| 9–20s | Open **Edit rules**. Inspect the category descriptions and boundary guidance. | “Find each document—not just each category.” |
| 20–36s | Run **Split document**. Show the real read stage and Jev decisions. | “Read every page. Find where each document begins.” |
| 36–50s | Select several returned segments. Corresponding source pages should change visibly in the preview and page strip. | “Every category connected to its original pages.” |
| 50–66s | Inspect the two Treasury auction results: separate financial-report segments on packet pages **4** and **5**. Frame the **Same category · separate document** divider and the changing dates, security identifiers, or titles on the source pages. | “Same category. Distinct documents.” |
| 66–78s | Download one segment and open the exported PDF. Verify its content against the selected source pages. | “Export each original document as its own PDF.” |
| 78–90s | Frame measured timings, download **Result JSON**, and show the optional real-document pilot with its narrow sample counts. | “Categories, page ranges, and measured speed.” |

The expected boundaries are pages **1–3** (tax form), **4** (42-day Treasury result), **5** (91-day Treasury result), and **6–15** (the complete BEA release). Use the observed results honestly. Do not force a success narrative over an incorrect boundary. Correct data/rule issues before freezing the final demonstration, and retain any limitations in the accompanying documentation.

## Evidence and editing

- Both finished videos keep all retained footage at real speed, including the complete OCR, inference, and export processing intervals. Idle pauses and unrelated navigation are cut; processing is not accelerated.
- Full pipeline includes conversion, OCR, decisions, validation, and split export. It excludes UI thumbnail rendering. **OCR cache hit** identifies reused parsing; never call that a fresh OCR benchmark.
- Native category probabilities are Jev scores, not calibrated guarantees of correctness.
- The optional panel says **Real-document pilot · saved runs**. Its source/run counts remain visible. Three repetitions of one document are three timing observations, not three independent accuracy examples. This is a demonstration, not broad evidence of production accuracy.
- The previous synthetic evaluation is separate. The app does not display that evaluation for the real set unless a matching real summary is provided. No numerical claim may be transferred from the synthetic corpus to these originals.
- Keep original captions/SRT files and final 1080p MP4s. Retain raw captures and editing notes outside the public source archive. Use real source/result frames for thumbnails.

## Synthetic fixtures are retained separately

`JEV_DOCS_DEMO_SET=synthetic docjev demo` loads the original generated sample set for repeatable tests. It visibly says **Synthetic test fixtures** and labels source previews accordingly. The synthetic corpus remains useful for unit tests, boundary regression tests, and controlled evaluation; it is not the material for these two public demo videos.

## Local app API

- `GET /api/samples`: IDs, display names, formats, editable rules, provider-readiness booleans, selected `demo_set`, and safe provenance links/notes. Ground-truth labels and filesystem paths are omitted.
- `POST /api/runs`: multipart `task=classify|split`, exactly one `sample_id` or `file`, `rules` as `RuleSet` JSON, `ocr=liteparse|llamaparse`, and `tier=cost_effective|agentic|agentic_plus`; optional `engine=jev|openai`, `model`, `use_cache`. Returns 202 and an opaque run ID. The visible app uses Jev.
- `GET /api/runs/{id}`: status/stage, elapsed wall time, document provenance, result or error, preview URLs, download URLs. Poll while queued/parsing/deciding.
- `GET /api/runs/{id}/assets/{token}`: an asset registered by that run; `?download=true` requests an attachment. There is no client-supplied filesystem path endpoint.
- `GET /api/comparison`: sanitized saved aggregates from `benchmarks/results/latest-summary.json`, or the newest `benchmarks/results/*/summary.json`. A real pilot must explicitly carry `demo_set: "real"`. The UI pairs concurrency-1 Jev and LLM measurements for the same task and scope and shows source/run counts prominently.

All operations reuse the shared parser, classifier, splitter, and exporter. The app rejects non-localhost hosts and cross-origin mutations, keeps credentials server-side, limits uploads to 30 MB, and serializes local processing. It is a local demonstration app, not a production upload service.

## Actual recorded flow

This appendix is the authoritative description of the finished videos. Both recordings reviewed and applied existing preset rules; they did not make a meaningful wording edit. All retained footage plays at 1×, including the complete OCR, Jev and export processing intervals. The classification download-popover sequence is omitted. Splitting includes a supplementary real download click and a real one-page PDF view from the same successful run; no new inference was performed for that ending.

### Classification — 76.4 seconds

| Finished time | Actual footage |
|---|---|
| 0.0–3.0s | Branded opening card. |
| 3.0–13.0s | Start with the original document. An original 10-page BEA release: charts, notes, and statistical tables. Source linked in the app. |
| 13.0–25.5s | Define categories in plain language. Review editable category descriptions and document-level instructions. The whole document informs one decision. |
| 25.5–33.4s | Choose the OCR layer. LiteParse runs locally by default. LlamaParse offers Cost-effective, Agentic, and Agentic Plus modes. |
| 33.4–39.8s | Read, then classify. Actual processing, shown at normal speed: LiteParse reads all 10 pages, then Jev applies the rules. |
| 39.8–46.5s | Inspect the decision and timings. Press Release. Jev: 326 ms. Reading: 4.34 s. Full pipeline: 4.76 s for this run. |
| 46.5–55.4s | Inspect the source pages. Browse the original pages alongside the result and category probabilities. Structured JSON is available. |
| 55.4–63.9s | Compare measured decision speed. Saved pilot: Jev 182 ms vs. GPT-5.6 Luna 785 ms median. One source, three timed runs per model. |
| 63.9–68.4s | Try another document. A Treasury auction report uses the same rules and OCR path. This second run is also shown at normal speed. |
| 68.4–72.9s | Reuse the workflow. Financial Report. Jev: 312 ms. Full pipeline: 875 ms. Timings are measured for this one-page report. |
| 72.9–76.4s | Branded closing card and independent-demo notice. |

### Splitting — 96.8 seconds

| Finished time | Actual footage |
|---|---|
| 0.0–3.0s | Branded opening card. |
| 3.0–9.0s | Start with a combined packet. Four complete public documents, combined into one 15-page packet. Original pages are unchanged. |
| 9.0–17.0s | Trace the source documents. The packet combines IRS Form 941, two Treasury auction reports, and a BEA release. Original sources are linked. |
| 17.0–25.0s | Review the category rules. Category descriptions identify tax forms, financial reports, press releases, and legal notices. |
| 25.0–31.5s | Review the boundary instructions. Keep separate Treasury auctions apart. Keep each publication’s continuation pages together. |
| 31.5–40.6s | Read every page, then split. Actual processing at normal speed: LiteParse reads all 15 pages; Jev predicts categories and document starts. |
| 40.6–47.3s | Inspect the recovered documents. Four documents. Jev: 557 ms. Reading: 5.55 s. Full pipeline, including export: 6.27 s. |
| 47.3–53.3s | Inspect the first Treasury report. Packet page 4: the 42-day Treasury bill auction. Its own Financial Report segment. |
| 53.3–60.3s | Preserve the next document boundary. Packet page 5: a different Treasury auction. The same category, with a separate document boundary. |
| 60.3–68.3s | Keep the complete release together. The BEA release remains one document across packet pages 6–15, including its tables and technical notes. |
| 68.3–73.8s | Verify the source pages. Packet page 11 is a statistical table inside the same Press Release segment. |
| 73.8–80.3s | Compare measured decision speed. Saved pilot: Jev 294 ms vs. GPT-5.6 Luna 1.59 s median. One packet, three timed runs per model. |
| 80.3–86.3s | Download the selected document. The selected Treasury report exports as its own PDF. Four PDFs and result JSON are available. |
| 86.3–93.3s | Open the exported PDF. One page, matching packet page 4. The exported PDFs and result JSON accompany this demo. |
| 93.3–96.8s | Branded closing card and independent-demo notice. |

The [media documentation](media/README.md) links both MP4s, captions, editable timelines, per-run evidence, verification reports, and [the actual four-PDF output archive](media/split-output.zip). Raw recordings are local unpublished provenance; public evidence uses relative paths and checksums, with no local absolute paths. The Treasury category card in the classification second run is above the captured viewport; its Financial Report probability label and measured timings are visible.

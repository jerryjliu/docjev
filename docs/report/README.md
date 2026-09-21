# Classify in 139 ms. Split in 210 ms.

A visual field report from DocJev’s **40-document / eight-packet** accuracy run, in LlamaIndex’s brand style.

![DocJev benchmark summary: Jev classified 40/40 documents and split 7/8 packets exactly, versus Luna’s 40/40 and 8/8. Jev median decision times were 139 ms and 210 ms.](summary.png)

**[Open the live report](https://jerryjliu.github.io/docjev/)** — no download or local server needed.

The hosted report loads original-page previews as needed. To create a single self-contained file that works offline, run:

```sh
uv run python scripts/build_visual_report.py --standalone output/docjev-report-offline.html
```

The offline export embeds the fonts, all 116 original-page previews, and recorded results. Neither version makes inference calls.

- Explore every classification, filter by category, and inspect timings and review flags.
- Compare the original boundaries with both engines’ segments across all eight packets.
- Replay the recorded median timings at real speed; this is an illustration, not a live model run.
- Enlarge the authentic FOMC pages to see Jev’s one extra split.

The [summary PNG](summary.png) is ready for a README, post, or presentation. The full report also adapts to mobile screens and supports browser printing.

The same LiteParse text was shared between engines. These are single-pass results on a curated sample of English public-sector PDFs; the eight packets reuse the 40 originals. Labels received separate agent review, with no human annotation review. Decision times exclude OCR. Costs are estimates from recorded usage, with local compute excluded.

[Full numerical report](../../benchmarks/results/real-small-v1-run01/report.md) · [Error analysis](../../benchmarks/results/real-small-v1-run01/error-analysis.md) · [Raw results](../../benchmarks/results/real-small-v1-run01/raw.jsonl) · [Dataset](../../datasets/real-small/README.md) · [Rights and attribution](../../datasets/real-small/v1/NOTICE.md)

## Rebuild offline

From the repository root:

```sh
uv run python scripts/build_visual_report.py
```

This validates source PDF hashes and reconciles accuracy, medians, costs, and paired OCR hashes against the saved observations before generating `data.json`, authentic previews, and `index.html` from `template.html`. It does not read credentials, private OCR text, or call either model. Bundled fonts include their license text; copies and asset provenance are in [assets](assets/NOTICE.md).

To regenerate the PNG, install the optional browser renderer once:

```sh
uv run --with playwright playwright install chromium
uv run --with playwright python scripts/capture_visual_report.py
```

The capture uses the report’s `?share=1` layout at 1200 pixels wide. `REPORT_CHROMIUM_PATH` can point to an already installed Chromium executable. The HTML and PNG do not require Playwright to view.

## Publishing

The `visual report` GitHub Actions workflow publishes the committed report to [GitHub Pages](https://jerryjliu.github.io/docjev/). It stages only the HTML, summary image, public data, and attributed report assets. Rebuild and commit these artifacts when editing the template; pushing `main` deploys them. No API keys or inference calls are involved. The workflow follows [GitHub’s custom Pages workflow](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

The explorer includes all 116 original pages, with clickable segment ranges, page navigation, and zoom. The headline cards use the same visual scale and font size for both engines, with accuracy next to latency. The CLI examples require a local checkout and a TypeSafe key; the report itself is read-only.

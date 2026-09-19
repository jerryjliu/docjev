# Short live comparisons

Two silent, captioned screen recordings with no intro or outro slide. Original document pages occupy almost half the app, alongside independent Jev and GPT-5.6 Luna results. Both submit clicks occur within the first second; the complete inference intervals remain at normal speed.

| Video | Length | Run starts | Jev result appears | Both results appear |
|---|---:|---:|---:|---:|
| [Classification](classification.mp4) | 24.0 s | 0.23 s | 0.60 s | 1.40 s |
| [Splitting](splitting.mp4) | 24.1 s | 0.53 s | 1.03 s | 3.07 s |

These are approximate **video positions**, distinct from the measured model decision times below. Use the supplied [classification thumbnail](classification-thumbnail.png) and [splitting thumbnail](splitting-thumbnail.png) for result-first previews; both are frames from the delivered videos.

## Actual recorded results

| Task | Source and outcome | Jev decision | Luna decision | Shared conversion + OCR |
|---|---|---:|---:|---:|
| Classification | Complete 10-page BEA release → `press_release` | 382.988 ms | 1,183.922 ms | 4.23 s |
| Splitting | 15-page packet → four source documents | 456.699 ms | 2,503.747 ms | 5.72 s |

Splitting returns `tax_form` on pages 1–3, two separate `financial_report` documents on pages 4 and 5, and `press_release` on pages 6–15. The two adjacent Treasury reports have different auction dates, security terms, and CUSIPs. The BEA tables stay with their original publication. All predicted labels/ranges were checked against the demo manifest and original pages.

These are **one recorded comparison per task**, not a general speed or accuracy benchmark. Both clients are prepared before launch, receive the same normalized LiteParse text and category/boundary rules, then start concurrently with zero retries. Decision timing excludes OCR, thumbnail preparation, and PDF export. Different model prompt/output schemas implement the same task semantics. The separate [sequential pilot](../../../benchmarks/results/real-doc-pilot-20260919/report.md) has its own conditions and results.

Fresh OCR does not imply a cold provider cache. The final classification request reports 13,113 cached OpenAI input tokens out of 13,116; the splitting request reports no cached reads. Jev cache usage is unreported. Request-level usage and estimated costs are preserved, including cache details. The two displayed comparison pairs cost an estimated $0.006465258 in total; this is usage-based estimation, not an invoice.

## Capture correction and provenance

Classification required one capture correction: the recorder countdown caused the first take to start after Jev had finished. That earlier pair was 712.451 ms / 2,378.521 ms; its [unchanged run evidence](classification-incomplete-capture.run.json) remains available. The final classification video uses only the second run's actual footage and results. Splitting uses its first run. No fastest-of-many selection or cross-run result substitution was performed. All three pairs together cost an estimated $0.010401198.

The pages are original IRS, Treasury, and BEA publications. The splitting packet concatenates complete originals with unchanged pages; it is a constructed packet of real documents. [Provenance and assembly map](../../../examples/real/SOURCE.json) identify the sources. No synthetic-looking replacement pages were created.

Raw videos were captured continuously at 1670 × 1080. The crop `[0,118,1670,962]` removes OS/browser chrome and retains the in-app logo and OCR footer. The finished H.264 files are 1920 × 1080, 30 fps, with a thin caption strip and no audio. Cropped app footage is scaled proportionally; UI and cursor movement are genuine. Both the recorder's small native pointer and the highlighted interaction cursor are present in the source footage.

Only setup, navigation, and idle result-reading time are omitted. No part of either model-execution interval is accelerated or cut. Rules are the existing presets reviewed after the result; no wording change is claimed on camera. Browser download-history panels are wholly excluded. The social clips show segmentation results; the [PDF export bundle](../split-output.zip) belongs to the earlier long walkthrough and is labeled separately.

## Reusable assets

| Artifact | Classification | Splitting |
|---|---|---|
| Video | [MP4](classification.mp4) | [MP4](splitting.mp4) |
| Result thumbnail | [PNG](classification-thumbnail.png) | [PNG](splitting-thumbnail.png) |
| Captions | [SRT](classification.srt) | [SRT](splitting.srt) |
| Timeline | [JSON](classification.edit.json) | [JSON](splitting.edit.json) |
| Unchanged exported run | [JSON](classification.run.json) | [JSON](splitting.run.json) |
| Hashes and provenance | [JSON](classification.evidence.json) | [JSON](splitting.evidence.json) |
| Edit report | [JSON](classification.report.json) | [JSON](splitting.report.json) |
| Contact sheet | [JPG](classification-contactsheet.jpg) | [JPG](splitting-contactsheet.jpg) |

Both complete MP4s were decoded and reviewed at full size, including ordered motion frames through startup, result transitions, page selection, and edit boundaries. Local raw paths in the reports identify ignored working files; they are not bundled or publicly downloadable. API credentials, private browser chrome, and raw recordings are excluded from the release.

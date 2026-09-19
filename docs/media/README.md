# Recorded demos

For the new short videos with immediate live comparisons, see [social demos](social/README.md). The longer walkthroughs below remain available for setup, OCR choices, and PDF export.

Two captioned, silent walkthroughs of real document classification and splitting. Both use LiteParse locally and Jev `jev-1.13.0`. All retained application footage, including the complete processing intervals, plays at normal speed.

| Video | Length | What it shows |
|---|---:|---|
| [Classification](classification.mp4) | 76.4 seconds | A complete BEA release, reviewed category rules, OCR choices, a live classification, source tables, a saved pilot, and a second Treasury classification. |
| [Splitting](splitting.mp4) | 96.8 seconds | A 15-page packet, reviewed boundary rules, four recovered documents, separate adjacent Treasury reports, the complete BEA release, a saved pilot, and an actual PDF export. |

The sources are original U.S. government publications. The combined packet was assembled independently from complete source documents with their pages unchanged. This is an independent demo; no government endorsement is implied. [Source provenance](../../examples/real/SOURCE.json) records each original publication.

## Recorded results

| Input | Result | Jev decision | Read / OCR | Full pipeline |
|---|---|---:|---:|---:|
| BEA release, 10 pages | Press Release | 326 ms | 4.34 s | 4.76 s |
| Treasury auction, 1 page | Financial Report | 312 ms | 556 ms | 875 ms |
| Combined packet, 15 pages | 4 documents, covering every page | 557 ms | 5.55 s | 6.27 s |

These are the observed recorded runs, with fresh LiteParse parsing. Read / OCR includes conversion. Full pipeline includes decisions, validation and, for splitting, PDF export; UI thumbnail rendering is excluded. Native category probabilities are provider scores, not calibrated guarantees of correctness.

The saved comparison shown in each video is a separate, narrow [real-document pilot](../../benchmarks/results/real-doc-pilot-20260919/report.md): one classification source and one splitting packet, each with three timed runs per model at concurrency 1. Its decision timings exclude OCR. It does not establish general production accuracy or speed.

## Inspect the actual outputs

[Download the split outputs](split-output.zip): the four PDFs returned by the successful recorded split, plus its structured result JSON and a short README. Their page counts are 3, 1, 1, and 10; all 15 exported pages were checked against their corresponding canonical source pages. The export ending is a supplementary recording from the same successful run, with no new inference.

| Artifact | Classification | Splitting |
|---|---|---|
| Captions | [SRT](classification.srt) | [SRT](splitting.srt) |
| Contact sheet | [JPG](classification-contactsheet.jpg) | [JPG](splitting-contactsheet.jpg) |
| Editable timeline | [JSON](classification.edit.json) | [JSON](splitting.edit.json) |
| Recorded-run evidence | [JSON](classification.evidence.json) | [JSON](splitting.evidence.json) |
| Edit and verification report | [JSON](classification.report.json) | [JSON](splitting.report.json) |

## Capture and editing provenance

The raw recordings were captured continuously at 1670 × 1080. The final MP4s are silent H.264, 1920 × 1080 at 30 fps. Cropping removes browser chrome; authored LlamaIndex title cards, headers and captions frame the genuine application pixels and recorded cursor. No application screens, model outputs or cursor movement were fabricated. At most a few terminal frames repeat solely for frame-rate rounding.

Preset rules were reviewed and applied during both recordings; no meaningful wording edit was made on camera. The classification download-popover interval is entirely excluded. The splitting export ending retains the real download click and the real PDF viewer; browser navigation and local file paths are excluded. Complete files were decoded, key shots inspected at full resolution, and ordered frame sequences checked through processing, segment selection, and PDF navigation.

Raw recordings and editing intermediates remain local and unpublished under `output/recordings/`, which is ignored by the repository. The relative raw paths in timelines and evidence identify that local provenance; they are not downloadable files in this repository. SHA-256 digests bind the captured inputs, rules, raw videos and delivered files.

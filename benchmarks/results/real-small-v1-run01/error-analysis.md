# Error analysis: real-small-v1-run01

Reviewed September 19, 2026 by `/root/dataset_implementation` (agent). This is a post-run inspection of the recorded responses against the already frozen truth, source PDFs, and saved LiteParse text. No prompts, rules, labels, thresholds, source bytes, or recorded responses were changed; no inference was repeated.

## One extra attachment boundary

Jev's only scored error is in `p001`: it starts a new `press_release` segment at **packet page 9**, inserting a boundary **after page 8**. There are **no missed true boundaries and no incorrect page categories** in this packet. The baseline preserves the expected segmentation. The observations are `measured:split:p001:jev:0` and `measured:split:p001:openai:0` in [raw.jsonl](raw.jsonl), lines 42 and 41.

| Source | Frozen category | Expected packet pages | Jev packet pages |
|---|---|---|---|
| e001: IRS Form 1040 | tax_form | 1–2 | 1–2 |
| e002: IRS Form 940, including voucher | tax_form | 3–5 | 3–5 |
| e009: Treasury auction results | financial_report | 6 | 6 |
| e017: FOMC statement and implementation attachment | press_release | **7–10** | **7–8; 9–10** |
| e033: CDC food-safety handout | other | 11–12 | 11–12 |

Thus the expected internal boundary positions, expressed as the preceding page, are `{2, 5, 6, 10}`; Jev returns `{2, 5, 6, 8, 10}`. It correctly separates the adjacent tax forms after page 2. Its recorded start probability for page 9 is `0.76`, above the frozen `0.5` threshold; this is a provider score, not a calibrated probability of correctness.

The evidence supports retaining the frozen annotation:

- [Original e017](../../../datasets/real-small/v1/originals/e017.pdf), source page 2 / packet page 8, ends the statement and explicitly prints **“Attachment.”** Source page 3 / packet page 9 begins **“Decisions Regarding Monetary Policy Implementation,”** with the same July 30, 2025 release date, and relates the implementation decisions to that day's FOMC statement. Source page 4 continues that attachment. The [official PDF](https://www.federalreserve.gov/monetarypolicy/files/monetary20250730a1.pdf) contains all four pages as one supplied publication.
- The [frozen protocol](../../../datasets/real-small/v1/PROTOCOL.md) defines boundaries by original-publication identity, retaining supporting appendices. The [frozen split rules](../../../datasets/real-small/v1/rules/split.yaml) retain a release's supporting material and reject a new section alone as a boundary. The [pre-inference annotation](../../../datasets/real-small/v1/annotations.json) explicitly includes this implementation attachment; it was separately reviewed before predictions existed.
- The saved LiteParse text for packet pages 8–9 retains both the attachment cue and the implementation heading. Both engines received the same parsed-page hash, `fde89ea2a9f0cab3e1155ee450226b59cfcfd1e5a04463a84d7970d5013324b1`, recorded in their observations and [preparation.json](preparation.json). Jev processed the entire packet in one request, so this was not a request-window seam.

The new heading, repeated release timestamp, and statement closing mark offer a plausible explanation for the extra split. That explanation is an inference from the document layout, not evidence of the model's internal reasoning. Under a different task definition the attachment could be considered a separate logical document; this run scores the publication-based policy fixed before inference.

This single split explains Jev's 7/8 exact packets, 32/33 boundary precision, and 32/32 boundary recall while retaining 116/116 correct page categories across the split set. The [summary](summary.json) also records 39/40 exact labeled segments: splitting one true segment into two creates two unmatched predicted segments.

## Successful examples inspected

For each row below, both recorded engines match the frozen truth. Classification checks used the named rendered source pages and front/end text; split checks compared complete predicted segment lists with the source map and visually inspected the specified supporting pages.

| Task/input | Evidence inspected |
|---|---|
| Classification e002 → tax_form | IRS Form 940 page 1 and attached payment voucher page 3. |
| Classification e013 → financial_report | NCUA Share Insurance Fund cover, management overview, and charts on pages 1, 2, and 6. |
| Classification e019 → press_release | Census construction-spending announcement page 1 and statistical table page 3. |
| Classification e029 → legal_notice | NARA request-for-comments heading on page 1 and continuing schedules plus closing publication record on page 5. |
| Classification e033 → other | Both pages of the CDC Listeria prevention handout. Both engines also set `needs_review=true`; the correct category is not an unqualified acceptance signal. |
| Split p004: all five segments exact | Separate NRC and NSF notices at pages 1–3 and 4–5, including their closing pages; Treasury statement pages 6–9, retaining its sparse final footnotes; USDA release pages 10–11, retaining its survey-methodology continuation. |
| Split p008: all five segments exact | EPA notice pages 1–4, including continuing terms and closing authority; NCUA fund report pages 8–13, retaining cover, overview, and final cash-flow table; Census release pages 14–18, retaining explanatory notes and three statistical tables. |

Source identities and page mappings are in [SOURCE.json](../../../datasets/real-small/v1/SOURCE.json) and [packet-plan.json](../../../datasets/real-small/v1/packet-plan.json). This review also checked the complete FOMC source text and the rendered pages directly around the erroneous boundary. It is a targeted error analysis, not a second exhaustive audit of every successful response.

## Limits

This is one pass on 40 selected English government PDFs and eight constructed packets, not a representative production accuracy estimate or a test of repeatability. The same 40 originals supply both tasks; packet pages, segments, and boundaries are dependent observations, and some issuers share templates. Blank official tax forms and digital PDFs do not establish performance on completed private forms, scans, other languages, or arbitrary office documents. The corpus labels received separate agent review before the run, but **human review was not performed**. This post-run reviewer was also the initial corpus annotator; inspection against immutable evidence does not create an independent human adjudication.

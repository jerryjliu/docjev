# Synthetic fixture gallery

The documents listed on this page are synthetic, editable or reproducible, and safe to redistribute under the [dataset dedication](../datasets/LICENSE). No genuine customer or personal records are included. The default app and public videos instead use the separate [real public-document collection](../examples/real/README.md).

## Classification inbox

| Source | Expected category | What it exercises |
|---|---|---|
| [d01.pdf](../examples/classify/inbox/d01.pdf) | invoice | Two pages, including a title-free service-detail continuation |
| [d02.pdf](../examples/classify/inbox/d02.pdf) | purchase_order | Image-only grayscale scan with mild rotation |
| [d03.docx](../examples/classify/inbox/d03.docx) | contract | Two-page Word agreement and Office pagination |
| [d04.docx](../examples/classify/inbox/d04.docx) | resume | One-page candidate history |
| [d05.pptx](../examples/classify/inbox/d05.pptx) | pitch_deck | Editable three-slide investor presentation |
| [d06.pdf](../examples/classify/inbox/d06.pdf) | other | An unrelated observatory field guide |

The [classification rules](../examples/classify/rules.yaml) describe document purpose. Neutral source filenames intentionally avoid giving the engine a filename shortcut.

## Claim packet

The [nine-page packet](../examples/split/claim-packet.pdf) contains six source documents:

| Pages | Category | Document |
|---|---|---|
| 1-2 | claim_form | Loss statement and supporting details |
| 3 | incident_report | Facilities incident record |
| 4-5 | repair_estimate | Proposed repair scope and conditions |
| 6-7 | invoice | First supplier's invoice and work log |
| 8 | invoice | A second supplier's separate invoice |
| 9 | correspondence | Claims-desk letter |

The adjacent invoice boundary before page 8 is the central example: equal categories do not imply one source document. The [splitting rules](../examples/split/rules.yaml) explicitly define this behavior.

## Evaluation files

The [dataset card](../datasets/DATASET_CARD.md) documents the 60 classification sources and 24 split packets, generation conditions, isolation, licensing, and limits. Exact labels, original hashes, and page ranges are in [classify.json](../datasets/manifests/classify.json) and [split.json](../datasets/manifests/split.json). Demo documents are separate from held-out evaluation data.

The [format fixtures](../examples/fixtures/manifest.json) contain related three-page PDF, DOCX, and PPTX presentations with the same business claims. They support conversion checks and must not count as three independent accuracy samples.

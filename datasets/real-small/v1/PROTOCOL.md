# Small real-document pilot: source selection protocol

Version 1.0.0. Selection protocol recorded before corpus acquisition or inference on September 19, 2026.

Select 40 complete English-language authentic PDFs, eight each of `tax_form`, `financial_report`, `press_release`, `legal_notice`, and `other`, using the existing real-demo taxonomy. Prefer short government-authored publications with official download and source-specific redistribution evidence. Seek different purposes, issuers, and layouts where available. Do not treat publication dates alone as a new template family. This is a convenience sample, not a random sample or an unseen-template benchmark.

Preserve every selected original byte and every page. Do not generate content, fill tax forms, manufacture scans, print web pages to PDF, excerpt publications, or add separators. Authentic blank forms are eligible and identified as blank. Exclude existing demo originals, revisions of those publications, exact duplicate files, obvious near-duplicate editions, ambiguous purpose, incomplete or corrupt files, unclear redistribution rights, and candidates incompatible with the page budget. Record downloaded exclusions and reasons. Candidate replacements happen before freeze and never depend on model predictions.

The 40 originals together contain at most 160 pages. Each is classified once and appears exactly once in one of eight constructed packets. Every packet contains five complete originals and at most 25 pages. At least four packets contain adjacent distinct originals with the same category. Packet boundaries follow original-publication identity, including instructions, tables, vouchers, or appendices that are part of the same original.

Labels use document purpose, supported by source text and actual rendered pages. The corpus agent proposes labels; a separate root-agent pass checks all labels and completeness before freeze. Record reviewer identity and method honestly. No independent human annotation or human adjudication is claimed; human review remains `not_performed` unless a person actually reviews it. Resolve disagreements before inference or log and replace ambiguous candidates.

Inference receives normalized page text and the frozen general rules only. Neutral local IDs and filenames identify inputs. Titles, labels, provenance, and assembly maps remain outside prompts. Preserve original embedded metadata rather than rewriting authentic files.

Use the existing BEA document and finance packet only as two `dev` entries: one excluded warmup per task and engine, four warmup task invocations total. They are not among the 40 scored originals. There is no new development corpus. Record these dependencies in freeze identity.

The measured study is one LiteParse pass per task input, one classification/splitting pass per engine, concurrency one, no retries, and a $2 local estimated admission guard. There are 96 measured task invocations plus four excluded warmups; provider request count can differ. There are 40 unique source documents, 48 scored task inputs, 40 expected split segments, and 32 internal boundaries. Cross-task source reuse is deliberate; report task scores separately.

Freeze selected sources, annotations and actual review state, rules, packet plan, manifests, source provenance, and assembly-tool identity. Verification is offline and read-only. Changes after freeze require a new corpus version and invalidate prepared evaluation receipts. Report failures and unexpected results without tuning or rerunning.

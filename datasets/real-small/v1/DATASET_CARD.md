# Real-small v1

A convenience sample of 40 authentic, complete English PDFs for document classification, with the same originals used exactly once across eight constructed splitting packets. There are 116 unique source pages and 232 scored task-input pages. This small pilot has eight documents per category and eight five-document packets, without synthetic documents, fabricated scans, or added separator pages.

| Category | Originals | Source pages | Coverage |
|---|---:|---:|---|
| tax_form | 8 | 25 | Eight distinct blank IRS tax forms, including instructions, vouchers, and worksheets |
| financial_report | 8 | 30 | Three distinct security auction types, Treasury cash/debt statement, four NCUA funds |
| press_release | 8 | 24 | Federal Reserve policy, Census statistics, BEA investment, USDA statistical/organizational announcements |
| legal_notice | 8 | 27 | Eight atomic Federal Register public-inspection publications across seven agency groups |
| other | 8 | 10 | Food safety, handwashing, fire safety, a blank planning worksheet, emergency preparedness |

Classification labels describe the whole publication's purpose. Tables, instructions, covers, vouchers and implementation attachments remain part of that publication. The two rules files preserve the existing real-demo categories, adding financial-position/income/expense/cash-flow language so financial statements are explicitly covered. Rules and labels were established before inference.

Annotations were proposed by `/root/dataset_implementation`, then checked in a separate `/root` agent review of all pages using full-page contact sheets and source-text passages. No independent human annotation or human adjudication was performed. Exact reviewed source hashes and purpose evidence are in [annotations.json](annotations.json); source bytes/provenance are in [SOURCE.json](SOURCE.json). The excluded-candidate log records unavailable downloads and existing demo publications. No source replacement is based on model output.

There is no new training or development corpus. Classification's existing BEA demo source and splitting's existing 15-page finance packet are two globally distinct `dev` entries, excluded from scoring. They produce four warmup task invocations across two engines. All five old demo originals and revisions of those particular publications are excluded from the scored originals.

The test manifests contain 40 classification documents and eight packets. Each packet has five originals, totaling 40 truth segments and 32 internal boundaries. Four packets have a boundary between adjacent distinct sources of the same category. See [packet-plan.json](packet-plan.json) for exact assignments and page provenance. Page streams, boxes, rotation and every rendered page are checked against the originals during freeze.

Source dependence is deliberate and must be reported. The same 40 originals appear in both tasks. IRS, public-inspection notices, NCUA fund reports, Treasury auctions, USFA handouts and USDA releases share issuer/layout families. The four NCUA reports cover distinct funds in the same month; they are not repeated date-only editions. Neutral filenames do not remove the actual agency names and headers in the documents. This is not an unseen-template or unseen-issuer test.

The study supports counts and error inspection on these particular inputs. It does not establish production accuracy, representative customer-workload performance, native Office/scan/handwriting/multilingual accuracy, or accuracy on naturally assembled packet streams. Classification changes by 2.5 percentage points per document; packet exact match changes by 12.5 points per packet. It is inappropriate to present eight correlated packets as a broad accuracy estimate.

The one-pass experiment is LiteParse only, with identical normalized text shared between engines, no label/provenance metadata in prompts, four excluded warmup task invocations, 96 measured task invocations, concurrency one, and a $2 local estimated guard. Corpus preparation and the later paid-stage result are distinct; consult the benchmark result directory for actual execution status and scores. No score is claimed in this card.

For source-specific rights, CDC attribution and non-endorsement notices, and the USFA/NFPA sharing basis, read [NOTICE.md](NOTICE.md). Real documents are excluded from the synthetic CC0 dedication.

Verify offline from the repository root:

```sh
uv run python datasets/real-small/prepare.py --verify --render
uv run pytest tests/test_real_small_integrity.py tests/test_real_examples.py tests/test_dataset_integrity.py
```

`--verify` is read-only and does not download, repair, or update hashes. Changing a frozen source, rule, annotation, plan or manifest invalidates verification and preparation receipts. `FREEZE.json` records the exact corpus, assembly-tool and warmup dependency identities, plus the renderer version used for the complete pixel comparison.

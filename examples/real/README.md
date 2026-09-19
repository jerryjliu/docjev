# Real public-finance documents

These are authentic, publicly issued U.S. government PDFs downloaded from official sources. The source layouts, dates, figures, and pages are preserved. The collection supports a public-finance inbox demonstration: route each publication by purpose, then separate a packet into its original publications.

The combined packet was assembled for this independent software demonstration. It is not a packet issued by the government. The named agencies do not sponsor or endorse this project.

| File | Source publication | Pages | Demo category |
| --- | --- | ---: | --- |
| `originals/r01.pdf` | [IRS Form 941, revised March 2026](https://www.irs.gov/pub/irs-pdf/f941.pdf) | 3 | `tax_form` |
| `originals/r02.pdf` | [Treasury 42-day bill auction result, August 12, 2025](https://fiscaldata.treasury.gov/static-data/published-reports/auctions-query/results/R_20250812_1.pdf) | 1 | `financial_report` |
| `originals/r03.pdf` | [Treasury 91-day bill auction result, May 12, 2025](https://fiscaldata.treasury.gov/static-data/published-reports/auctions-query/results/R_20250512_2.pdf) | 1 | `financial_report` |
| `originals/r04.pdf` | [BEA Personal Income and Outlays, July 2025](https://www.bea.gov/news/2025/personal-income-and-outlays-july-2025) | 10 | `press_release` |
| `originals/r05.pdf` | [SEC Form 18 public-comment notice, FR Doc. 2025-11513](https://www.govinfo.gov/app/details/FR-2025-06-24/2025-11513) | 2 | `legal_notice` |

The IRS file is an official blank form, including its payment voucher; no fictitious taxpayer information was inserted. The other files are actual issued publications. The SEC file is the complete public-inspection PDF, before Federal Register typesetting, downloaded from the official Office of the Federal Register host. Historical economic estimates are preserved as published and may since have been revised.

`SOURCE.json` records each download URL, source title, issuer, publication date, page count, exact byte count, SHA-256, and redistribution basis. Neutral filenames avoid exposing category labels through filenames. The demo labels and page map are separate from model input.

## Splitting example

`public-finance-packet.pdf` contains four complete source PDFs in this order:

| Packet pages | Source | Expected category |
| --- | --- | --- |
| 1–3 | IRS Form 941, including its voucher | `tax_form` |
| 4 | 42-day Treasury bill auction result | `financial_report` |
| 5 | 91-day Treasury bill auction result | `financial_report` |
| 6–15 | Complete BEA release, including technical notes and statistical tables | `press_release` |

Pages 4 and 5 demonstrate a boundary between adjacent documents of the same category: their auction dates, CUSIPs, and security terms differ. Pages 6–15 demonstrate that charts, notes, and dense table continuations remain with their source release. Rules explicitly define auction results as financial reports despite their generic news-release header.

No separator pages, watermarks, covers, or handwritten labels were added. PDF objects are reserialized when the packet is assembled, so its file bytes differ from the original downloads. All source page content streams and page dimensions match, and all 15 packet pages were rendered and compared pixel-for-pixel with their corresponding original pages during preparation. The originals retain their exact downloaded bytes. Blank IRS form fields remain blank.

## Use and verification

From the repository root:

```sh
docjev classify examples/real/originals/r04.pdf --rules examples/real/classify/rules.yaml
docjev split examples/real/public-finance-packet.pdf --rules examples/real/split/rules.yaml
uv run python examples/real/assemble.py --verify
```

`assemble.py` without `--verify` rebuilds the packet from the hash-checked originals and updates its manifest hash. It makes no network or model requests. Treat rebuilding as a change to a frozen demo input; rerun measurements if the packet or rules change.

The canonical manifest is `demo-manifest.json`. These five documents and one deliberately assembled packet are demonstration cases, not an independent accuracy benchmark or representative evaluation dataset. The existing synthetic dev/test datasets remain separate. Warmups and repeated measurements on these examples cannot support a held-out generalization claim.

## Redistribution and attribution

Source: U.S. Internal Revenue Service; U.S. Department of the Treasury, Bureau of the Fiscal Service; U.S. Bureau of Economic Analysis; and U.S. Securities and Exchange Commission / Office of the Federal Register.

These selected government-authored publications are public-domain U.S. government works under [17 U.S.C. § 105](https://www.copyright.gov/title17/92chap1.html#105). The [IRS content policy](https://www.irs.gov/about-irs/use-of-content-from-irsgov), [BEA reuse policy](https://www.bea.gov/help/faq/147), and [National Archives description of the Federal Register](https://www.archives.gov/federal-register/the-federal-register/about.html) explain the relevant reuse basis. The Treasury auction results are agency-authored factual reports of official auctions. No third-party photography or illustrations were identified in the selected PDFs; the BEA charts and tables are its own statistical publications.

Government names, seals, and logos retain their legal protections. They appear only within the unchanged source documents to identify their issuers. They are not project branding, and their inclusion does not imply approval, sponsorship, affiliation, or endorsement. These source documents are not covered by the repository's code license or the synthetic dataset's CC0 dedication.

# Limits and interpretation

- Jev requires hosted API access. Open-source code and local OCR do not make the entire pipeline offline.
- The initial release supports PDF, DOCX, and PPTX. Office rendering requires LibreOffice and can depend on installed fonts; results refer to the retained canonical PDF.
- Splits occur between pages. No within-page cuts, noncontiguous reconstruction, or native Office fragment editing is supported.
- Category changes create boundaries. A wrong page label can therefore over-segment a document; conflicts are surfaced for review. The benchmark includes boundary quality, not just page labels.
- Very large whole-document classification is rejected. Splitting uses windows but still rejects an individual required page/context combination that exceeds the supported input size. Local token estimates are not exact provider counts.
- Jev probabilities and confidence are provider outputs, not proof of correctness. The default review threshold is an operational convenience. No production calibration claim is made.
- Blankness is conservative: a visibly nonblank page with no readable text fails instead of being silently labeled `other`.
- The published real-document pilot repeats one original document and one assembled packet three times per engine. It establishes agreement on those examples and their observed decision times, not held-out accuracy or general performance. Provider caches were uncontrolled; Luna's measured inputs were almost entirely cached.
- The separate 60-document / 24-packet synthetic corpus is primarily English and uses a limited set of document styles. Source/template separation supports controlled evaluation; its full benchmark has not been run, and no synthetic accuracy result is claimed.
- Client location, concurrency, provider prompt caches, model revisions, and parser versions affect speed and cost. Saved benchmark results describe the recorded configuration and date.
- LlamaParse `latest` may not reveal its resolved parser version in every response. That fact is recorded; a floating version is not described as fully reproducible.
- The local app is a demo, with in-process jobs and no durable queue. Restarting it clears active job state. Do not expose it publicly as a hosted service.

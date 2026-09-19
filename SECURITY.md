# Security and data handling

DocJev is a local development tool. The demo binds to `127.0.0.1` and has no production authentication or multi-tenant isolation; keep it local.

LiteParse extracts text on your machine. Classification and splitting send that text to TypeSafe. Selecting OpenAI sends the same text to OpenAI. Selecting LlamaParse uploads the canonical PDF to LlamaCloud for OCR. Only use documents you are authorized to send to the selected provider.

Environment variables hold API credentials. The web UI never receives them. Local `.jev-docs/` caches and run assets contain document content; they are ignored by Git. Remove these artifacts when you no longer need them, and do not include them in public releases.

Treat downloaded documents as untrusted. The project validates file types, uses isolated conversion profiles, and checks page coverage, but does not provide an operating-system sandbox for PDF/Office parsers. Use an isolated environment for untrusted external files.

For a suspected vulnerability, contact the repository maintainer privately through the published GitHub profile rather than posting credentials or document content in a public issue.


# Contributing

Install Python 3.11 or 3.12 and uv, then run `uv sync --all-extras`.

```sh
uv run ruff check .
uv run mypy src/jev_docs
uv run pytest
uv build
```

Ordinary tests use local fixtures and mocked provider responses; they do not require API keys. Live checks are opt-in and can incur charges. Keep credentials in environment variables, never fixtures or commits.

Preserve the page contract: one-based source pages, no silent omissions, exact ordered coverage, and explicit failures. Keep LiteParse/LlamaParse OCR separate from Jev/LLM decisions. Changes to prompts, thresholds, datasets, or prices need new versioned benchmark runs; do not overwrite published observations.

When adding a sample, use fictional or clearly licensed content and record its source, license, page labels, and hash. Never infer ground truth from the engine under evaluation. Hold related template families and source variants in the same dataset split.

Use the public Classify/Split docs only as shape references. Do not add dependencies on LlamaIndex's hosted classification or splitting implementation.


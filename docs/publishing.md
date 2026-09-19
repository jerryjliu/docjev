# Publishing DocJev

The destination repository is [jerryjliu/docjev](https://github.com/jerryjliu/docjev). The source, package, and video assets are prepared locally; publishing them is a separate step from renaming the project.

## Repository

From this project directory, review the files, create the initial commit, and push to [DocJev](https://github.com/jerryjliu/docjev). Inspect `git remote -v` first; skip the `remote add` command below if `origin` already points to this repository. The local release ZIP, `output/release/docjev-0.1.0.zip`, can also be unpacked into a fresh checkout.

```sh
git init
git add .
git commit -m "Add DocJev document classification and splitting demo"
git branch -M main
git remote add origin https://github.com/jerryjliu/docjev.git
git push -u origin main
```

If `origin` points elsewhere, confirm the intended destination before changing it. The package name and primary CLI are `docjev`; availability on PyPI has not been checked or reserved. Python imports remain `jev_docs`, and the older `jev-docs` CLI continues to work. Existing recordings and measured run artifacts retain their original names and evidence.

## Demo assets

- Short social videos: [Classification](media/social/classification.mp4) and [Splitting](media/social/splitting.mp4), with [thumbnails, captions, and run evidence](media/social/README.md).
- Longer walkthroughs: [Classification](media/classification.mp4) and [Splitting](media/splitting.mp4).
- [Actual split PDFs and JSON](media/split-output.zip).
- [Source provenance](../examples/real/README.md) and [measured timing report](../benchmarks/results/real-doc-pilot-20260919/report.md).

The videos are silent, captioned 1080p recordings. They can be uploaded directly as release assets or shared with the repository link. Every retained processing sequence plays at normal speed. The short clips show individual concurrent comparisons; the longer walkthroughs show a separate saved pilot with three timed repeats on one source per task. Neither establishes general accuracy. Keep that scope with any benchmark numbers reused in a post.

The repository includes source code, original public demo documents, separate synthetic evaluation fixtures, and all their notices. Local credentials, document caches, virtual environments, and raw screen recordings are excluded from the clean release archive.

## Local verification

```sh
uv sync --all-extras --locked
uv run ruff check .
uv run mypy src/jev_docs
uv run pytest
uv build
```

These checks passed locally on macOS with Python 3.12: 85 tests passed and three opt-in live OCR tests were excluded. The configured GitHub Actions matrix has not yet run remotely. The optional full synthetic benchmark has not been executed.

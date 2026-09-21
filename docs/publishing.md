# Publishing DocJev

The destination repository is [jerryjliu/docjev](https://github.com/jerryjliu/docjev). The [initial release commit](https://github.com/jerryjliu/docjev/commit/3a68115e9a910219adf6457afb2f79e74ff7601e) has been pushed and its [GitHub checks](https://github.com/jerryjliu/docjev/actions/runs/35458387718) passed. The accuracy corpus, runner, results, and visual report are included in the follow-up repository release.

## Repository

The current source bundle is `output/release/docjev-0.1.0.zip`, with a per-file release manifest and SHA-256 sidecar. The follow-up commits include the complete benchmark evidence and [interactive visual report](report/README.md).

The package name and primary CLI are `docjev`; availability on PyPI has not been checked or reserved. Python imports remain `jev_docs`, and the older `jev-docs` CLI continues to work. Existing recordings and measured run artifacts retain their original names and evidence.

## Visual report

The [live visual benchmark report](https://jerryjliu.github.io/docjev/) includes a page explorer and a [shareable summary image](report/summary.png). GitHub Pages deploys the committed public report from `main`. The [rebuild instructions](report/README.md) also produce an optional self-contained offline HTML export. The report makes no model calls. Keep its small-sample scope and exact-packet accuracy visible when sharing speed figures.

## Demo assets

- Short social videos: [Classification](media/social/classification.mp4) and [Splitting](media/social/splitting.mp4), with [thumbnails, captions, and run evidence](media/social/README.md).
- Longer walkthroughs: [Classification](media/classification.mp4) and [Splitting](media/splitting.mp4).
- [Actual split PDFs and JSON](media/split-output.zip).
- [Source provenance](../examples/real/README.md) and [measured timing report](../benchmarks/results/real-doc-pilot-20260919/report.md).
- Separate [40-document accuracy report](../benchmarks/results/real-small-v1-run01/report.md), [error analysis](../benchmarks/results/real-small-v1-run01/error-analysis.md), and [dataset notices](../datasets/real-small/v1/NOTICE.md).

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

These checks passed locally on macOS with Python 3.12: 190 offline tests passed and three opt-in live OCR tests were excluded. The prior release and benchmark report passed GitHub Actions on Linux/macOS and Python 3.11/3.12; the workflow runs again on every push. All corpus pages passed rendered equality checks; source archives include the evaluation corpus while the wheel excludes it. The optional full synthetic benchmark has not been executed.

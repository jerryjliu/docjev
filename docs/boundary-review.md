# Boundary review signals

A confident category does not imply a confident document boundary. `split_document` now exposes structured `review_reasons` on each segment and sets `needs_review` when any reason exists.

| Reason | Meaning |
|---|---|
| `boundary_near_threshold` | A native boundary score is within `boundary_review_margin` of `boundary_threshold`. |
| `category_uncertain` | A page's selected-category score is below `min_probability`. |
| `category_boundary_conflict` | A category change forced a boundary despite a continuation decision. |
| `other_category` | The catch-all category was selected. |

Every reason records the one-based page. Score-based reasons also carry `probability` and `threshold`. For `boundary_near_threshold`, the page is the page **after** the candidate boundary. An uncertain cut marks both adjacent segments; an uncertain continuation marks its containing segment. The segmentation itself is unchanged.

```sh
uv run docjev split examples/real/public-finance-packet.pdf \
  --rules examples/real/split/rules.yaml \
  --boundary-threshold 0.5 --boundary-review-margin 0.1
```

The Python API accepts the same `boundary_review_margin` keyword. Its default is 0.1, so scores in [0.4, 0.6] trigger review with the default decision threshold of 0.5. The interval follows a custom threshold and includes its endpoints; margin 0 disables the signal. Scores outside [0, 1] remain invalid. Scores are provider outputs, not calibrated error probabilities.

The first page, blank-page blocks, and boundaries forced by the blank-page policy do not trigger this signal. Providers without boundary probabilities, including the current Luna adapter, do not receive invented scores. Missing scores mean the signal is unavailable, not that a boundary is safe.

This is a general review heuristic, not a learned calibration or an attachment repair rule. Its margin was not fitted to the v1 error. The known FOMC extra cut scored 0.76 and would **not** be caught by the default band. The published v1 results and review flags remain unchanged. Do not use this known failure to tune a threshold and then report improvement on the same data.

The [next challenge protocol](../datasets/real-challenge/README.md) freezes thresholds before fresh examples are scored. Report boundary review precision/recall and review workload separately from segmentation accuracy. Review can identify mistakes; it does not automatically correct them.

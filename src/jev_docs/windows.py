"""Exact page ownership and deliberately conservative context estimates."""

import json
from dataclasses import dataclass

from .errors import ContextLimitError
from .schemas import Page

# Serialized UTF-8 bytes are intentionally conservative; these are not tokenizer counts.
MAX_STATE_QUESTION_BYTES = 95_000
MAX_REQUEST_BYTES = 190_000


def check_budget(state: dict, questions: dict) -> None:
    size = len(json.dumps(state, ensure_ascii=False).encode())
    lengths = [len(json.dumps(q, ensure_ascii=False).encode()) for q in questions.values()]
    if (
        size + max(lengths, default=0) > MAX_STATE_QUESTION_BYTES
        or size + sum(lengths) > MAX_REQUEST_BYTES
    ):
        raise ContextLimitError(
            "Input exceeds the conservative Jev context budget. No text was truncated."
        )


@dataclass
class PageWindow:
    pages: list[Page]
    targets: list[Page]


def window_for(pages: list[Page], start: int, end: int) -> PageWindow:
    """Indices start:end own outputs; adjacent context never owns a second output."""
    return PageWindow(pages[max(0, start - 1) : min(len(pages), end + 1)], pages[start:end])


def page_windows(pages: list[Page], size: int = 8) -> list[PageWindow]:
    if size < 1:
        raise ValueError("Window size must be positive")
    return [window_for(pages, i, min(i + size, len(pages))) for i in range(0, len(pages), size)]

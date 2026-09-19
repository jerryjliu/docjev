import pytest
from hypothesis import given
from hypothesis import strategies as st

from jev_docs.engines.jev import JevEngine
from jev_docs.errors import ProviderError
from jev_docs.schemas import Page, PageDecision
from jev_docs.split import asplit_document, assemble_segments
from jev_docs.windows import page_windows, window_for


def test_same_category_instances_stay_separate(document, rules):
    decisions = [
        PageDecision(page=i, category="invoice", starts_document=i in {1, 3}) for i in range(1, 5)
    ]
    segments, warnings = assemble_segments(decisions, document, rules)
    assert [s.pages for s in segments] == [[1, 2], [3, 4]]
    assert not warnings


def test_category_boundary_conflict_is_visible(document, rules):
    decisions = [
        PageDecision(
            page=i, category="invoice" if i < 3 else "purchase_order", starts_document=i == 1
        )
        for i in range(1, 5)
    ]
    segments, warnings = assemble_segments(decisions, document, rules)
    assert [s.pages for s in segments] == [[1, 2], [3, 4]]
    assert segments[1].needs_review
    assert "Page 3" in warnings[0]


def test_blank_page_policy_preserves_source(document, rules):
    document.pages[1] = Page(number=2, text="", blank=True)
    decisions = [
        PageDecision(page=i, category="invoice", starts_document=i == 1) for i in range(1, 5)
    ]
    segments, _ = assemble_segments(decisions, document, rules)
    assert [(s.category, s.pages) for s in segments] == [
        ("invoice", [1]),
        ("other", [2]),
        ("invoice", [3, 4]),
    ]


def test_missing_or_duplicate_decisions_rejected(document, rules):
    with pytest.raises(ProviderError):
        assemble_segments([PageDecision(page=1, category="invoice")], document, rules)


@given(length=st.integers(1, 120), size=st.integers(1, 30))
def test_windows_own_every_page_once(length, size):
    pages = [Page(number=i, text="content") for i in range(1, length + 1)]
    windows = page_windows(pages, size)
    assert [p.number for w in windows for p in w.targets] == list(range(1, length + 1))
    for window in windows:
        first = window.targets[0].number
        if first > 1:
            assert window.pages[0].number == first - 1


def test_question_instructions_identify_target_pages(document, rules):
    questions = JevEngine.split_questions(window_for(document.pages, 2, 4), rules)
    assert "page number 3" in questions["category_3"].instructions
    assert "page number 3" in questions["boundary_3"].instructions
    assert "page number 2" in questions["boundary_3"].instructions
    assert "category_2" not in questions  # Context page has no duplicate owner.


async def test_full_result_has_complete_coverage(document, rules):
    class Engine:
        name = "fixture"
        model = "fixture"

        async def split(self, doc, rules, **options):
            return [
                PageDecision(page=i, category="invoice", starts_document=i in {1, 3})
                for i in range(1, 5)
            ], []

    result = await asplit_document(document, rules, engine=Engine())
    assert [p for s in result.segments for p in s.pages] == [1, 2, 3, 4]

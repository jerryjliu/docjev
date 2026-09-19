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


def test_preflight_is_pure_and_refines_the_same_local_windows(document, rules, monkeypatch):
    from jev_docs.engines import jev
    from jev_docs.engines.openai import OpenAIEngine

    def forbidden(*args, **kwargs):
        pytest.fail("Pure preflight constructed a client")

    monkeypatch.setattr(jev, "AsyncTypeSafeClient", forbidden)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    for page in document.pages:
        page.text = "x" * 30_000
    planned = JevEngine.planned_split_windows(document, rules)
    checked = JevEngine.preflight(document, rules, "split")
    assert checked == {"request_count": 2, "windows": [[1, 2], [3, 4]]}
    assert checked["windows"] == [[page.number for page in window.targets] for window in planned]
    assert OpenAIEngine.preflight(document, rules, "split")["request_count"] == 1
    with pytest.raises(Exception, match="budget"):
        JevEngine.preflight(document, rules, "classify")


async def test_live_split_uses_the_pure_window_plan(document, rules):
    from types import SimpleNamespace

    engine = object.__new__(JevEngine)
    engine.context_recovery = False
    engine.window_size = 8
    for page in document.pages:
        page.text = "x" * 30_000
    seen = []

    async def request(state, questions, task):
        seen.append(sorted(int(key.split("_")[1]) for key in questions if key.startswith("category_")))
        return SimpleNamespace(
            choices={key: SimpleNamespace(choice="invoice", probabilities={"invoice": 1}, confidence=1)
                     for key in questions if key.startswith("category_")},
            nouls={key: SimpleNamespace(noul=0) for key in questions if key.startswith("boundary_")},
        ), []

    engine._request = request
    decisions, _ = await engine.split(document, rules)
    assert seen == JevEngine.preflight(document, rules, "split")["windows"]
    assert [page.page for page in decisions] == [1, 2, 3, 4]


@pytest.mark.parametrize("recovery", [False, True])
async def test_remote_context_recovery_is_opt_in_for_bounded_profile(document, rules, recovery):
    from types import SimpleNamespace

    from jev_docs.errors import ContextLimitError
    from jev_docs.schemas import RequestRecord

    engine = object.__new__(JevEngine)
    engine.context_recovery = recovery
    engine.window_size = 8
    seen = []
    rejection = RequestRecord(provider="jev", model="fixture", task="split", status="error", error_code="413")

    async def request(state, questions, task):
        seen.append(questions)
        if len(seen) == 1:
            raise ContextLimitError("Provider rejected context", requests=[rejection])
        return SimpleNamespace(
            choices={key: SimpleNamespace(choice="invoice", probabilities={"invoice": 1}, confidence=1)
                     for key in questions if key.startswith("category_")},
            nouls={key: SimpleNamespace(noul=0) for key in questions if key.startswith("boundary_")},
        ), []

    engine._request = request
    if recovery:
        decisions, records = await engine.split(document, rules)
        assert len(seen) == 3 and len(decisions) == 4
        assert records == [rejection]
    else:
        with pytest.raises(ContextLimitError) as raised:
            await engine.split(document, rules)
        assert len(seen) == 1 and raised.value.requests == [rejection]


def test_both_adapters_preflight_reject_blank_classification(document, rules):
    from jev_docs.engines.openai import OpenAIEngine
    from jev_docs.errors import DocumentError

    for page in document.pages:
        page.text = ""
        page.blank = True
    for adapter in (JevEngine, OpenAIEngine):
        with pytest.raises(DocumentError, match="blank"):
            adapter.preflight(document, rules, "classify")
    assert JevEngine.preflight(document, rules, "split")["request_count"] == 0


def test_baseline_preflight_uses_live_payload_limit(document, rules):
    from jev_docs.engines.openai import OpenAIEngine
    from jev_docs.errors import ContextLimitError

    document.pages[0].text = "x" * 500_001
    with pytest.raises(ContextLimitError):
        OpenAIEngine.preflight(document, rules, "split")
    with pytest.raises(ContextLimitError):
        OpenAIEngine.checked_payload(document, rules)

import pytest

from jev_docs.classify import aclassify_document
from jev_docs.engines.base import CategoryDecision
from jev_docs.errors import ContextLimitError, DocumentError, ProviderError
from jev_docs.schemas import RequestRecord
from jev_docs.windows import check_budget


class Engine:
    name = "fixture"
    model = "fixture-1"

    async def classify(self, doc, rules):
        assert len(doc.pages) == doc.page_count
        return CategoryDecision(
            "invoice", {"invoice": 0.62, "purchase_order": 0.28, "other": 0.10}, 0.35
        ), [
            RequestRecord(
                provider=self.name,
                model=self.model,
                task="classify",
                cost_usd=0.001,
                cost_status="estimated",
            )
        ]


async def test_scores_are_distinct_and_review_threshold(document, rules):
    result = await aclassify_document(document, rules, engine=Engine())
    assert result.category_probability == 0.62
    assert result.provider_confidence == 0.35
    assert result.needs_review
    assert result.metrics.decision_cost_usd == 0.001
    assert "canonical_path" not in result.document


async def test_unknown_output_is_failure(document, rules):
    class Bad(Engine):
        async def classify(self, doc, rules):
            return CategoryDecision("secret-label"), []

    with pytest.raises(ProviderError):
        await aclassify_document(document, rules, engine=Bad())


async def test_all_blank_is_not_success(document, rules):
    for page in document.pages:
        page.text = ""
        page.blank = True
    with pytest.raises(DocumentError):
        await aclassify_document(document, rules, engine=Engine())


def test_both_context_budgets():
    with pytest.raises(ContextLimitError):
        check_budget({"text": "x" * 96_000}, {"q": {"text": "short"}})
    with pytest.raises(ContextLimitError):
        check_budget({"text": "short"}, {str(i): {"text": "x" * 50_000} for i in range(4)})
    check_budget({"text": "short"}, {"q": {"text": "short"}})

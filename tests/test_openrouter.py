import json

import httpx
import pytest

from jev_docs.classify import aclassify_document
from jev_docs.engines import jev as jev_module
from jev_docs.engines import make_engine
from jev_docs.engines.openrouter import OpenRouterJevEngine, retry_after_ms
from jev_docs.errors import ContextLimitError, ProviderError
from jev_docs.split import asplit_document

# The real body OpenRouter returned for a ~2 MB state during manual verification.
LIVE_OVERSIZE_BODY = {
    "error": {
        "message": 'HTTP 400: {"detail":{"error_type":"max_tokens_exceeded"}}',
        "code": 400,
    }
}
OVERSIZE_CASES = [
    (413, {"error": {"code": 413, "message": "Payload exceeds limit"}}),
    (400, LIVE_OVERSIZE_BODY),
]


def decisions_payload(questions, *, cost=0.00021, split_at=frozenset({1})):
    answers = {}
    for key, question in questions.items():
        if question["type"] == "choice":
            answers[key] = {
                "type": "choice",
                "choice": "invoice",
                "confidence": 0.93,
                "probabilities": {
                    name: 0.97 if name == "invoice" else 0.03 / (len(question["criteria"]) - 1)
                    for name in question["criteria"]
                },
            }
        else:
            page = int(key.split("_")[1])
            answers[key] = {"type": "noul", "noul": 0.9 if page in split_at else 0.1}
    usage = {"input_tokens": 1200, "output_tokens": 4}
    if cost is not None:
        usage["cost"] = cost
    return {
        "id": "gen-dec-123",
        "model": "typesafe/jev-1.13-20260917",
        "provider": "TypeSafe",
        "answers": answers,
        "usage": usage,
    }


@pytest.fixture
async def engine_with():
    clients = []

    def build(handler, **kwargs):
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        clients.append(client)
        return OpenRouterJevEngine(api_key="test-key", http_client=client, **kwargs)

    yield build
    for client in clients:
        await client.aclose()


@pytest.fixture
def no_sleep(monkeypatch):
    delays = []

    async def record(delay):
        delays.append(delay)

    monkeypatch.setattr(jev_module.asyncio, "sleep", record)
    return delays


def answering(seen=None, update=None, **payload_kwargs):
    def handler(request):
        body = json.loads(request.content)
        if seen is not None:
            seen.append((request, body))
        payload = decisions_payload(body["questions"], **payload_kwargs)
        if update:
            update(payload)
        return httpx.Response(200, json=payload)

    return handler


def failing_first(status=None, *, headers=None, body=None):
    calls = []
    succeed = answering()

    def handler(request):
        calls.append(request)
        if len(calls) > 1:
            return succeed(request)
        if status is None:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(status, headers=headers, json=body or {"error": {"code": status}})

    return handler, calls


async def test_classify_sends_decisions_request_and_reports_billed_cost(
    document, rules, engine_with
):
    seen = []
    result = await aclassify_document(document, rules, engine=engine_with(answering(seen)))

    request, body = seen[0]
    assert str(request.url) == "https://openrouter.ai/api/alpha/decisions"
    assert request.headers["authorization"] == "Bearer test-key"
    assert request.headers["http-referer"] == "https://github.com/jerryjliu/docjev"
    assert request.headers["x-openrouter-title"] == "DocJev"
    assert body["model"] == "typesafe/jev-1.13"
    category = body["questions"]["category"]
    assert category["type"] == "choice"
    assert isinstance(category["instructions"], str) and category["instructions"]
    assert {"invoice", "purchase_order"} <= set(category["criteria"])
    assert body["state"]

    assert result.category == "invoice"
    assert result.engine == "openrouter"
    record = result.metrics.requests[0]
    assert record.provider == "openrouter"
    assert record.model == "typesafe/jev-1.13-20260917"
    assert record.request_id == "gen-dec-123"
    assert (record.input_tokens, record.output_tokens) == (1200, 4)
    assert record.cost_usd == pytest.approx(0.00021)
    assert record.cost_status == "reported"
    assert result.metrics.decision_cost_usd == pytest.approx(0.00021)


async def test_missing_cost_is_unknown_rather_than_estimated(document, rules, engine_with):
    result = await aclassify_document(document, rules, engine=engine_with(answering(cost=None)))
    assert result.metrics.requests[0].cost_usd is None
    assert result.metrics.requests[0].cost_status == "unknown"


async def test_split_maps_choice_and_noul_answers(document, rules, engine_with):
    engine = engine_with(answering(split_at=frozenset({1, 3})))
    result = await asplit_document(document, rules, engine=engine)
    assert [segment.pages for segment in result.segments] == [[1, 2], [3, 4]]


async def test_rate_limit_is_retried_with_retry_after_seconds(
    document, rules, engine_with, no_sleep
):
    handler, calls = failing_first(429, headers={"retry-after": "2"})
    result = await aclassify_document(document, rules, engine=engine_with(handler))
    assert len(calls) == 2
    assert no_sleep == [2.0]
    assert [record.status for record in result.metrics.requests] == ["error", "ok"]
    assert result.metrics.requests[0].error_code == "429"


@pytest.mark.parametrize("status", [503, 524, 529])
async def test_transient_statuses_are_retried(document, rules, engine_with, no_sleep, status):
    handler, calls = failing_first(status)
    result = await aclassify_document(document, rules, engine=engine_with(handler))
    assert len(calls) == 2
    assert result.metrics.requests[0].error_code == str(status)


@pytest.mark.parametrize("status", [400, 401, 402])
async def test_terminal_statuses_fail_once_without_leaking_the_body(
    document, rules, engine_with, no_sleep, status
):
    body = {"error": {"code": status, "message": "secret-detail"}}
    handler, calls = failing_first(status, body=body)
    with pytest.raises(ProviderError) as caught:
        await aclassify_document(document, rules, engine=engine_with(handler))
    assert len(calls) == 1
    assert [record.error_code for record in caught.value.requests] == [str(status)]
    assert str(status) in str(caught.value)
    assert "secret-detail" not in str(caught.value)


async def test_retry_exhaustion_keeps_every_attempt(document, rules, engine_with, no_sleep):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(529, json={"error": {"code": 529}})

    with pytest.raises(ProviderError) as caught:
        await aclassify_document(document, rules, engine=engine_with(handler, max_retries=2))
    assert len(calls) == 3
    assert [record.error_code for record in caught.value.requests] == ["529"] * 3


def test_unusable_retry_after_falls_back_to_backoff():
    for value in ("nan", "inf", "soon", "", None):
        assert retry_after_ms(value) == 0


async def test_retry_after_beyond_cap_fails_instead_of_retrying_early(
    document, rules, engine_with, no_sleep
):
    handler, calls = failing_first(429, headers={"retry-after": "30"})
    with pytest.raises(ProviderError):
        await aclassify_document(document, rules, engine=engine_with(handler))
    assert len(calls) == 1
    assert no_sleep == []


@pytest.mark.parametrize(("status", "body"), OVERSIZE_CASES)
async def test_oversized_input_raises_context_error_without_truncating(
    document, rules, engine_with, status, body
):
    def handler(request):
        return httpx.Response(status, json=body)

    with pytest.raises(ContextLimitError):
        await aclassify_document(document, rules, engine=engine_with(handler))


@pytest.mark.parametrize(("status", "body"), OVERSIZE_CASES)
async def test_split_recovers_from_size_rejection_with_smaller_windows(
    document, rules, engine_with, status, body
):
    targets = []

    def handler(request):
        payload = json.loads(request.content)
        pages = sorted(
            int(key.split("_")[1]) for key in payload["questions"] if key.startswith("category_")
        )
        targets.append(pages)
        if len(pages) > 2:
            return httpx.Response(status, json=body)
        return httpx.Response(
            200, json=decisions_payload(payload["questions"], split_at=frozenset({1, 3}))
        )

    result = await asplit_document(document, rules, engine=engine_with(handler))

    assert targets[0] == [1, 2, 3, 4]
    assert sorted(page for window in targets[1:] for page in window) == [1, 2, 3, 4]
    assert [segment.pages for segment in result.segments] == [[1, 2], [3, 4]]
    records = result.metrics.requests
    assert records[0].status == "error" and records[0].error_code == str(status)
    assert [record.status for record in records[1:]] == ["ok"] * (len(targets) - 1)


async def test_connection_errors_are_retryable(document, rules, engine_with, no_sleep):
    handler, _ = failing_first()
    result = await aclassify_document(document, rules, engine=engine_with(handler))
    assert result.metrics.requests[0].error_code == "ConnectionError"


@pytest.mark.parametrize(
    "update",
    [
        lambda p: p.pop("answers"),
        lambda p: p["answers"].update(category={"type": "secret-detail"}),
        lambda p: p["usage"].update(cost="secret-detail"),
        lambda p: p["answers"]["category"]["probabilities"].update(invoice="secret-detail"),
        lambda p: p["answers"]["category"].pop("probabilities"),
    ],
)
async def test_malformed_responses_are_redacted_and_recorded(document, rules, engine_with, update):
    with pytest.raises(ProviderError) as caught:
        await aclassify_document(document, rules, engine=engine_with(answering(update=update)))
    assert "secret-detail" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert [record.error_code for record in caught.value.requests] == ["MalformedDecisionsResponse"]


@pytest.mark.parametrize(
    "update",
    [
        lambda p: p["answers"]["category"].update(probabilities={}),
        lambda p: p["answers"]["category"].update(probabilities={"invoice": 0.97}),
    ],
)
async def test_classify_rejects_partial_probabilities(document, rules, engine_with, update):
    with pytest.raises(ProviderError, match="invalid category decision") as caught:
        await aclassify_document(document, rules, engine=engine_with(answering(update=update)))
    assert [record.status for record in caught.value.requests] == ["ok"]


async def test_caller_owned_client_stays_open_and_owned_client_closes():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    try:
        await OpenRouterJevEngine(api_key="k", http_client=client).aclose()
        assert not client.is_closed
    finally:
        await client.aclose()

    owned = OpenRouterJevEngine(api_key="k")
    await owned.aclose()
    assert owned.http.is_closed


def test_missing_key_explains_which_variable_to_set(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="OPENROUTER_API_KEY"):
        OpenRouterJevEngine()


async def test_factory_selects_openrouter_with_pinned_default_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    pinned = make_engine("openrouter")
    latest = make_engine("openrouter", "~typesafe/jev-latest")
    try:
        assert isinstance(pinned, OpenRouterJevEngine)
        assert pinned.model == "typesafe/jev-1.13"
        assert latest.model == "~typesafe/jev-latest"
    finally:
        await pinned.aclose()
        await latest.aclose()

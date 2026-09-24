"""Jev categorical and boundary decisions with measured, bounded requests."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, RetryPolicy

from ..errors import ContextLimitError, DocumentError, ProviderError
from ..schemas import PageDecision, ParsedDocument, RequestRecord, RuleSet
from ..windows import PageWindow, check_budget, page_windows, window_for
from .base import (
    BOUNDARY_POLICY,
    UNTRUSTED,
    CategoryDecision,
    classification_instructions,
    page_state,
)


class JevEngine:
    name = "jev"

    def __init__(
        self,
        model: str = "jev-1.13.0",
        *,
        api_key: str | None = None,
        timeout: float = 30,
        max_retries: int = 1,
        window_size: int = 8,
        context_recovery: bool = True,
    ):
        if not (api_key or os.getenv("TYPESAFE_API_KEY")):
            raise ProviderError(
                "Set TYPESAFE_API_KEY to use Jev. Get access at console.typesafe.ai."
            )
        self.model = model
        self.max_retries = max_retries
        self.window_size = window_size
        self.context_recovery = context_recovery
        self.client = AsyncTypeSafeClient(
            api_key=api_key, model=model, timeout=timeout, retry=RetryPolicy(max_retries=0)
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    async def _request(
        self, state: dict, questions: dict, task: str
    ) -> tuple[Any, list[RequestRecord]]:
        check_budget(state, {k: q.model_dump() for k, q in questions.items()})
        records: list[RequestRecord] = []
        for attempt in range(1, self.max_retries + 2):
            started = time.perf_counter()
            try:
                response = await self.client.system_one(
                    state=state, questions=questions, model=self.model
                )
            except Exception as exc:
                status = getattr(exc, "status", None)
                records.append(
                    RequestRecord(
                        provider=self.name,
                        model=self.model,
                        task=task,
                        attempt=attempt,
                        status="error",
                        elapsed_ms=(time.perf_counter() - started) * 1000,
                        request_id=getattr(exc, "request_id", None),
                        error_code=str(status or type(exc).__name__),
                    )
                )
                # Read only to recognize a context error; never expose provider bodies in logs.
                message = str(getattr(exc, "body", "")).lower()
                if status in {400, 413, 422} and any(
                    word in message for word in ("context", "token", "too long", "too large")
                ):
                    raise ContextLimitError(
                        "Jev rejected the input size; no text was truncated.", requests=records
                    ) from None
                retryable = status in {408, 429, 500, 502, 503, 504} or isinstance(
                    exc, (ConnectionError, TimeoutError)
                )
                if retryable and attempt <= self.max_retries:
                    delay = max(0.5 * attempt, (getattr(exc, "retry_after_ms", 0) or 0) / 1000)
                    if delay <= 10:
                        await asyncio.sleep(delay)
                        continue
                raise ProviderError(
                    f"Jev request failed ({status or type(exc).__name__}). Check access, limits, or connectivity.",
                    requests=records,
                ) from None
            elapsed = (time.perf_counter() - started) * 1000
            tokens = response.usage.input_tokens
            request_id = response.raw_http_response.headers.get("x-typesafe-request-id")
            records.append(
                RequestRecord(
                    provider=self.name,
                    model=response.model,
                    task=task,
                    attempt=attempt,
                    elapsed_ms=elapsed,
                    request_id=request_id,
                    input_tokens=tokens,
                    output_tokens=response.usage.output_tokens,
                    cost_usd=None if tokens is None else tokens * 0.042 / 1_000_000,
                    cost_status="unknown" if tokens is None else "estimated",
                )
            )
            if set(response.answers) != set(questions):
                raise ProviderError("Jev returned an incomplete answer set.", requests=records)
            return response, records
        raise AssertionError("Unreachable retry state")

    @staticmethod
    def classification_questions(rules: RuleSet) -> dict:
        return {"category": Choice(
            instructions=classification_instructions(rules), criteria=rules.criteria
        )}

    async def classify(self, document: ParsedDocument, rules: RuleSet):
        response, records = await self._request(
            page_state(document.pages), self.classification_questions(rules), "classify"
        )
        answer = response.choices.get("category")
        if (
            answer is None
            or answer.choice not in rules.criteria
            or set(answer.probabilities) != set(rules.criteria)
        ):
            raise ProviderError("Jev returned an invalid category decision.", requests=records)
        return CategoryDecision(
            answer.choice, dict(answer.probabilities), answer.confidence
        ), records

    @staticmethod
    def split_questions(window: PageWindow, rules: RuleSet) -> dict:
        questions: dict = {}
        for page in window.targets:
            if page.blank:
                continue
            questions[f"category_{page.number}"] = Choice(
                instructions=(
                    UNTRUSTED + f"What document category does page number {page.number} belong to? "
                    "Use the neighboring pages to identify continuation pages whose title is absent. "
                    "Choose by the purpose of the source document, not individual words mentioned. "
                    + rules.instructions
                ),
                criteria=rules.criteria,
            )
            if page.number > 1:
                questions[f"boundary_{page.number}"] = Noul(
                    instructions=(
                        UNTRUSTED + BOUNDARY_POLICY + f"Does page number {page.number} start a new "
                        f"source document, rather than continue page number {page.number - 1}? "
                        + rules.splitting_instructions
                    )
                )
        return questions

    @classmethod
    def planned_split_windows(
        cls, document: ParsedDocument, rules: RuleSet, *, window_size: int = 8
    ) -> list[PageWindow]:
        """Resolve all local size checks before dispatch, without constructing a client."""
        def fits(window: PageWindow) -> None:
            check_budget(page_state(window.pages), {
                key: question.model_dump()
                for key, question in cls.split_questions(window, rules).items()
            })

        def refine(window: PageWindow) -> list[PageWindow]:
            try:
                fits(window)
                return [window]
            except ContextLimitError:
                if len(window.targets) == 1:
                    raise ContextLimitError(
                        "A required page and its context cannot fit Jev's input limit."
                    ) from None
                start = window.targets[0].number - 1
                end = window.targets[-1].number
                middle = (start + end) // 2
                return (refine(window_for(document.pages, start, middle))
                        + refine(window_for(document.pages, middle, end)))

        whole = window_for(document.pages, 0, document.page_count)
        try:
            fits(whole)
            return [whole]
        except ContextLimitError:
            return [part for window in page_windows(document.pages, window_size)
                    for part in refine(window)]

    @classmethod
    def preflight(
        cls, document: ParsedDocument, rules: RuleSet, task: str, *, window_size: int = 8
    ) -> dict:
        """Validate the exact request construction with no API key or client."""
        if task == "classify":
            if all(page.blank for page in document.pages):
                raise DocumentError("The document is blank; no model classification was attempted.")
            check_budget(page_state(document.pages), {
                key: question.model_dump()
                for key, question in cls.classification_questions(rules).items()
            })
            return {"request_count": 1, "windows": [[p.number for p in document.pages]]}
        if task != "split":
            raise ValueError("Task must be classify or split")
        windows = cls.planned_split_windows(document, rules, window_size=window_size)
        active = [window for window in windows if cls.split_questions(window, rules)]
        return {"request_count": len(active),
                "windows": [[page.number for page in window.targets] for window in active]}

    async def split(
        self, document: ParsedDocument, rules: RuleSet, *, boundary_threshold: float = 0.5
    ):
        decisions: list[PageDecision] = []
        records: list[RequestRecord] = []

        async def evaluate(window: PageWindow) -> None:
            questions = self.split_questions(window, rules)
            if not questions:
                decisions.extend(
                    PageDecision(page=p.number, category="other", starts_document=p.number == 1)
                    for p in window.targets
                )
                return
            try:
                response, calls = await self._request(page_state(window.pages), questions, "split")
                records.extend(calls)
            except ContextLimitError as exc:
                records.extend(exc.requests)
                if not self.context_recovery:
                    raise ContextLimitError(
                        "Jev rejected the prepared input size; context recovery is disabled.",
                        requests=records,
                    ) from None
                if len(window.targets) == 1:
                    raise ContextLimitError(
                        "A required page and its context cannot fit Jev's input limit.",
                        requests=records,
                    ) from None
                start = window.targets[0].number - 1
                end = window.targets[-1].number
                middle = (start + end) // 2
                await evaluate(window_for(document.pages, start, middle))
                await evaluate(window_for(document.pages, middle, end))
                return
            except ProviderError as exc:
                raise ProviderError(str(exc), requests=records + exc.requests) from None
            for page in window.targets:
                if page.blank:
                    decisions.append(
                        PageDecision(
                            page=page.number, category="other", starts_document=page.number == 1
                        )
                    )
                    continue
                answer = response.choices.get(f"category_{page.number}")
                boundary = response.nouls.get(f"boundary_{page.number}")
                if (
                    answer is None
                    or answer.choice not in rules.criteria
                    or answer.choice not in answer.probabilities
                    or (page.number > 1 and boundary is None)
                ):
                    raise ProviderError("Jev returned invalid page decisions.", requests=records)
                probability = 1.0 if page.number == 1 else boundary.noul
                decisions.append(
                    PageDecision(
                        page=page.number,
                        category=answer.choice,
                        category_probability=answer.probabilities[answer.choice],
                        probabilities=dict(answer.probabilities),
                        provider_confidence=answer.confidence,
                        starts_document=probability >= boundary_threshold,
                        starts_document_probability=probability,
                    )
                )

        windows = self.planned_split_windows(document, rules, window_size=self.window_size)
        for window in windows:
            await evaluate(window)
        return sorted(decisions, key=lambda d: d.page), records

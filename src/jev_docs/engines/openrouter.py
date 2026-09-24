"""Jev decisions through OpenRouter's Decisions API, sharing the direct engine's contract."""

from __future__ import annotations

import math
import os
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError
from typesafe_sdk import Answer, ChoiceAnswer, NoulAnswer
from typesafe_sdk import Usage as SDKUsage

from ..errors import ProviderError
from ..schemas import RequestRecord
from .jev import JevEngine

try:
    import httpx
except ImportError:
    raise ProviderError("Install docjev[openrouter] to use Jev through OpenRouter.") from None

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
ATTRIBUTION_HEADERS = {
    "HTTP-Referer": "https://github.com/jerryjliu/docjev",
    "X-OpenRouter-Title": "DocJev",
}


def _empty_if_null(value: Any) -> Any:
    return {} if value is None else value


class Usage(SDKUsage):
    model_config = ConfigDict(allow_inf_nan=False)

    cost: Annotated[float, Field(ge=0)] | None = None


class DecisionsResponse(BaseModel):
    """Reuses the SDK's answer types so both Jev engines hand JevEngine identical answers."""

    model_config = ConfigDict(strict=True)

    id: str | None = None
    model: str
    answers: dict[str, Answer]
    usage: Annotated[Usage, BeforeValidator(_empty_if_null)] = Field(default_factory=Usage)

    @property
    def choices(self) -> dict[str, ChoiceAnswer]:
        return {k: a for k, a in self.answers.items() if isinstance(a, ChoiceAnswer)}

    @property
    def nouls(self) -> dict[str, NoulAnswer]:
        return {k: a for k, a in self.answers.items() if isinstance(a, NoulAnswer)}


class DecisionsRequestError(Exception):
    """Carries only the fields JevEngine reads to classify, retry, or redact a failure."""

    def __init__(self, status: int, *, body: str = "", retry_after_ms: float = 0):
        super().__init__(f"OpenRouter Decisions request failed ({status})")
        self.status = status
        self.body = body
        self.retry_after_ms = retry_after_ms


class MalformedDecisionsResponse(Exception):
    """A 200 response that does not match the documented schema; never echoes its content."""

    def __init__(self, request_id: str | None = None):
        super().__init__("OpenRouter returned a malformed Decisions response")
        self.request_id = request_id


def parse_decisions(payload: Any) -> DecisionsResponse:
    try:
        return DecisionsResponse.model_validate(payload)
    except ValidationError:
        request_id = payload.get("id") if isinstance(payload, dict) else None
        raise MalformedDecisionsResponse(
            request_id if isinstance(request_id, str) else None
        ) from None


def retry_after_ms(value: str | None) -> float:
    """Parse Retry-After seconds; unusable values fall back to normal backoff."""
    try:
        seconds = float(value or 0)
    except ValueError:
        return 0
    return max(seconds, 0) * 1000 if math.isfinite(seconds) else 0


class OpenRouterJevEngine(JevEngine):
    name = "openrouter"
    # OpenRouter documents 524 and 529 as transient and 413 as a payload that is too large.
    retryable_statuses = JevEngine.retryable_statuses | {524, 529}
    context_limit_statuses = frozenset({413})

    def __init__(
        self,
        model: str = "typesafe/jev-1.13",
        *,
        api_key: str | None = None,
        timeout: float = 30,
        max_retries: int = 1,
        window_size: int = 8,
        context_recovery: bool = True,
        http_client: httpx.AsyncClient | None = None,
    ):
        key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not key:
            raise ProviderError(
                "Set OPENROUTER_API_KEY to use Jev through OpenRouter. "
                "Create a key at openrouter.ai/settings/keys."
            )
        self.model = model
        self.max_retries = max_retries
        self.window_size = window_size
        self.context_recovery = context_recovery
        self.headers = {"Authorization": f"Bearer {key}", **ATTRIBUTION_HEADERS}
        # aclose() leaves a caller-supplied client open.
        self.owns_http = http_client is None
        self.http = http_client or httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        if self.owns_http:
            await self.http.aclose()

    async def _decide(self, state: dict, questions: dict) -> DecisionsResponse:
        body = {
            "model": self.model,
            "state": state,
            "questions": {key: question.model_dump() for key, question in questions.items()},
        }
        try:
            response = await self.http.post(DECISIONS_URL, json=body, headers=self.headers)
        except httpx.TimeoutException:
            raise TimeoutError("OpenRouter request timed out") from None
        except httpx.TransportError:
            raise ConnectionError("OpenRouter connection failed") from None
        if response.status_code != 200:
            raise DecisionsRequestError(
                response.status_code,
                body=response.text,
                retry_after_ms=retry_after_ms(response.headers.get("retry-after")),
            )
        try:
            payload = response.json()
        except ValueError:
            raise MalformedDecisionsResponse() from None
        return parse_decisions(payload)

    def _success_record(
        self, response: DecisionsResponse, task: str, attempt: int, elapsed_ms: float
    ) -> RequestRecord:
        usage = response.usage
        return RequestRecord(
            provider=self.name,
            model=response.model,
            task=task,
            attempt=attempt,
            elapsed_ms=elapsed_ms,
            request_id=response.id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=usage.cost,
            cost_status="unknown" if usage.cost is None else "reported",
        )

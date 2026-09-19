"""A small, decision-only structured-output baseline; no invented confidence."""

from __future__ import annotations

import json
import os
import time
from typing import Any

from ..errors import ContextLimitError, DocumentError, ProviderError
from ..schemas import PageDecision, ParsedDocument, RequestRecord, RuleSet
from .base import (
    BOUNDARY_POLICY,
    UNTRUSTED,
    CategoryDecision,
    classification_instructions,
    page_state,
)


class OpenAIEngine:
    name = "openai"

    def __init__(self, model: str = "gpt-5.6-luna", *, timeout: float = 60):
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ProviderError("Install docjev[baseline] to use the OpenAI baseline.") from None
        if not os.getenv("OPENAI_API_KEY"):
            raise ProviderError("Set OPENAI_API_KEY to use the small LLM baseline.")
        self.model = model
        self.client = AsyncOpenAI(max_retries=0, timeout=timeout)

    async def aclose(self) -> None:
        await self.client.close()

    @staticmethod
    def checked_payload(document: ParsedDocument, rules: RuleSet) -> dict:
        payload = {"document": page_state(document.pages), "categories": rules.criteria}
        if len(json.dumps(payload).encode()) > 500_000:
            raise ContextLimitError(
                "The baseline's supported request-size limit was exceeded; no content was truncated."
            )
        return payload

    @classmethod
    def preflight(cls, document: ParsedDocument, rules: RuleSet, task: str) -> dict:
        """Check the same payload as live inference, without keys or an SDK client."""
        if task not in {"classify", "split"}:
            raise ValueError("Task must be classify or split")
        if task == "classify" and all(page.blank for page in document.pages):
            raise DocumentError("The document is blank; no model classification was attempted.")
        payload = cls.checked_payload(document, rules)
        return {"request_count": 1, "payload_bytes": len(json.dumps(payload).encode())}

    async def _request(
        self, document: ParsedDocument, rules: RuleSet, task: str, schema: dict, instructions: str
    ):
        started = time.perf_counter()
        payload = self.checked_payload(document, rules)
        kwargs: dict[str, Any] = (
            {"reasoning": {"effort": "none"}} if self.model.startswith(("gpt-5", "gpt-6")) else {}
        )
        try:
            response = await self.client.responses.create(
                model=self.model,
                instructions=instructions,
                input=json.dumps(payload, ensure_ascii=False),
                store=False,
                max_output_tokens=max(128, document.page_count * 45 + 100),
                text={
                    "format": {
                        "type": "json_schema",
                        "name": task,
                        "strict": True,
                        "schema": schema,
                    }
                },
                **kwargs,
            )
        except Exception as exc:
            code = str(getattr(exc, "status_code", None) or type(exc).__name__)
            record = RequestRecord(
                provider=self.name,
                model=self.model,
                task=task,
                status="error",
                elapsed_ms=(time.perf_counter() - started) * 1000,
                error_code=code,
            )
            raise ProviderError(
                f"OpenAI request failed ({code}). Check access or connectivity.", requests=[record]
            ) from None
        usage = response.usage
        input_tokens = usage.input_tokens if usage else None
        output_tokens = usage.output_tokens if usage else None
        details = usage.input_tokens_details if usage else None
        cached = getattr(details, "cached_tokens", 0) or 0
        writes = getattr(details, "cache_write_tokens", 0) or 0
        cost = None
        if input_tokens is not None and output_tokens is not None:
            if self.model.startswith("gpt-5.6-luna"):
                cost = (
                    max(0, input_tokens - cached - writes) * 0.20
                    + cached * 0.02
                    + writes * 0.25
                    + output_tokens * 1.20
                ) / 1e6
            elif self.model.startswith("gpt-4o-mini"):
                cost = (
                    max(0, input_tokens - cached) * 0.15 + cached * 0.075 + output_tokens * 0.60
                ) / 1e6
        record = RequestRecord(
            provider=self.name,
            model=response.model,
            task=task,
            request_id=getattr(response, "_request_id", None),
            elapsed_ms=(time.perf_counter() - started) * 1000,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached,
            cache_write_tokens=writes,
            reasoning_tokens=getattr(
                getattr(usage, "output_tokens_details", None), "reasoning_tokens", None
            ),
            cost_usd=cost,
            cost_status="estimated" if cost is not None else "unknown",
        )
        if response.status != "completed":
            record.status = "incomplete"
            raise ProviderError(
                "OpenAI returned an incomplete or refused decision.", requests=[record]
            )
        try:
            data = json.loads(response.output_text)
        except (ValueError, TypeError):
            record.status = "invalid"
            raise ProviderError(
                "OpenAI returned no valid structured decision.", requests=[record]
            ) from None
        return data, [record]

    async def classify(self, document: ParsedDocument, rules: RuleSet):
        schema = {
            "type": "object",
            "properties": {"category": {"type": "string", "enum": list(rules.criteria)}},
            "required": ["category"],
            "additionalProperties": False,
        }
        data, records = await self._request(
            document, rules, "classify", schema, classification_instructions(rules)
        )
        if data.get("category") not in rules.criteria:
            raise ProviderError("OpenAI returned an unknown category.", requests=records)
        return CategoryDecision(data["category"]), records

    async def split(
        self, document: ParsedDocument, rules: RuleSet, *, boundary_threshold: float = 0.5
    ):
        del boundary_threshold  # This baseline returns discrete decisions, not probabilities.
        segment = {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": list(rules.criteria)},
                "start": {"type": "integer"},
                "end": {"type": "integer"},
            },
            "required": ["category", "start", "end"],
            "additionalProperties": False,
        }
        schema = {
            "type": "object",
            "properties": {"segments": {"type": "array", "items": segment}},
            "required": ["segments"],
            "additionalProperties": False,
        }
        instruction = (
            UNTRUSTED + BOUNDARY_POLICY + "Split the full packet into ordered segments. "
            "Use inclusive 1-based start/end pages. Cover every page exactly once with no overlaps or gaps. "
            "Separate two adjacent source documents even if they share a category. "
            + rules.instructions
            + " "
            + rules.splitting_instructions
        )
        data, records = await self._request(document, rules, "split", schema, instruction)
        decisions: list[PageDecision] = []
        try:
            for segment in data["segments"]:
                start, end = segment["start"], segment["end"]
                if (
                    type(start) is not int
                    or type(end) is not int
                    or start < 1
                    or end < start
                    or end > document.page_count
                    or segment["category"] not in rules.criteria
                ):
                    raise ValueError("Invalid segment")
                decisions.extend(
                    PageDecision(page=p, category=segment["category"], starts_document=p == start)
                    for p in range(start, end + 1)
                )
            if [d.page for d in decisions] != list(range(1, document.page_count + 1)):
                raise ValueError("Missing or overlapping pages")
        except (KeyError, TypeError, ValueError):
            raise ProviderError(
                "OpenAI returned invalid segment coverage.", requests=records
            ) from None
        return decisions, records

"""Versioned public data contracts. Page numbers are always one-based."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CategoryRule(Model):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(min_length=1, max_length=4000)


class RuleSet(Model):
    schema_version: Literal["1"] = "1"
    categories: list[CategoryRule] = Field(min_length=1, max_length=255)
    instructions: str = Field(default="", max_length=8000)
    splitting_instructions: str = Field(default="", max_length=8000)

    @model_validator(mode="after")
    def validate_categories(self) -> RuleSet:
        ids = [c.id for c in self.categories]
        if len(ids) != len(set(ids)):
            raise ValueError("Category IDs must be unique")
        if "other" not in ids:
            if len(ids) >= 255:
                raise ValueError("Leave one category slot for the required 'other' fallback")
            self.categories.append(
                CategoryRule(
                    id="other",
                    description="None of the defined categories matches the document's purpose.",
                )
            )
        return self

    @property
    def criteria(self) -> dict[str, str]:
        return {c.id: c.description for c in self.categories}


class RequestRecord(Model):
    provider: str
    model: str
    task: str
    request_id: str | None = None
    attempt: int = 1
    status: str = "ok"
    elapsed_ms: float = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    cache_write_tokens: int | None = None
    reasoning_tokens: int | None = None
    cost_usd: float | None = None
    cost_status: Literal["estimated", "unknown", "reported", "not_applicable"] = "unknown"
    error_code: str | None = None


class RunMetrics(Model):
    conversion_ms: float = 0
    ocr_ms: float = 0
    decision_ms: float = 0
    validation_ms: float = 0
    export_ms: float = 0
    total_ms: float = 0
    ocr_cache_hit: bool = False
    ocr_cost_usd: float | None = None
    ocr_cost_status: str = "unknown"
    decision_cost_usd: float | None = None
    requests: list[RequestRecord] = Field(default_factory=list)


class ParserInfo(Model):
    name: str
    version: str
    tier: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    conversion: dict[str, Any] = Field(default_factory=dict)


class Page(Model):
    number: int = Field(ge=1)
    text: str
    markdown: str | None = None
    blank: bool = False


class ParsedDocument(Model):
    schema_version: Literal["1"] = "1"
    source_name: str
    source_sha256: str
    canonical_path: str
    canonical_sha256: str
    page_count: int = Field(ge=1)
    pages: list[Page]
    parser: ParserInfo
    metrics: RunMetrics = Field(default_factory=RunMetrics)

    @model_validator(mode="after")
    def complete_pages(self) -> ParsedDocument:
        if [p.number for p in self.pages] != list(range(1, self.page_count + 1)):
            raise ValueError("Parsed pages must cover every source page in order, exactly once")
        if any(not p.text.strip() and not p.blank for p in self.pages):
            raise ValueError("A nonblank page has no readable text")
        return self

    def public_info(self) -> dict[str, Any]:
        return {
            "name": self.source_name,
            "sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
            "page_count": self.page_count,
            "parser": self.parser.model_dump(),
        }


class PageDecision(Model):
    page: int = Field(ge=1)
    category: str
    category_probability: float | None = Field(default=None, ge=0, le=1)
    probabilities: dict[str, float] | None = None
    provider_confidence: float | None = Field(default=None, ge=0, le=1)
    starts_document: bool = False
    starts_document_probability: float | None = Field(default=None, ge=0, le=1)


class ReviewReason(Model):
    code: Literal[
        "other_category", "category_uncertain", "category_boundary_conflict",
        "boundary_near_threshold",
    ]
    page: int = Field(ge=1)
    probability: float | None = Field(default=None, ge=0, le=1)
    threshold: float | None = Field(default=None, ge=0, le=1)


class Segment(Model):
    id: str
    category: str
    pages: list[int] = Field(min_length=1)
    needs_review: bool = False
    review_reasons: list[ReviewReason] = Field(default_factory=list)
    mean_category_probability: float | None = None

    @model_validator(mode="after")
    def contiguous(self) -> Segment:
        if self.pages[0] < 1 or self.pages != list(range(self.pages[0], self.pages[-1] + 1)):
            raise ValueError("Segment pages must be positive, ordered, and contiguous")
        return self


class ClassificationResult(Model):
    schema_version: Literal["1"] = "1"
    task: Literal["classify"] = "classify"
    category: str
    category_probability: float | None = None
    probabilities: dict[str, float] | None = None
    provider_confidence: float | None = None
    needs_review: bool = False
    warnings: list[str] = Field(default_factory=list)
    document: dict[str, Any]
    engine: str
    model: str
    metrics: RunMetrics


class SplitResult(Model):
    schema_version: Literal["1"] = "1"
    task: Literal["split"] = "split"
    segments: list[Segment]
    page_decisions: list[PageDecision] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    document: dict[str, Any]
    engine: str
    model: str
    metrics: RunMetrics

    @model_validator(mode="after")
    def complete_segments(self) -> SplitResult:
        pages = [p for segment in self.segments for p in segment.pages]
        if pages != list(range(1, self.document["page_count"] + 1)):
            raise ValueError("Segments must cover all document pages exactly once, in order")
        return self

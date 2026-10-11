"""Public domain contracts for the VeriPlan workflow."""

from enum import Enum
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    """Reject client fields that the server, rather than the client, controls."""

    model_config = ConfigDict(extra="forbid")


class DecisionStatus(str, Enum):
    draft = "draft"
    clarifying = "clarifying"
    awaiting_confirmation = "awaiting_confirmation"
    planning = "planning"
    researching = "researching"
    analyzing = "analyzing"
    challenging = "challenging"
    delivering = "delivering"
    awaiting_review = "awaiting_review"
    accepted = "accepted"
    revised = "revised"
    deferred = "deferred"
    failed = "failed"
    retrying = "retrying"


class ResearchQueryStatus(str, Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class ResearchQuery(StrictModel):
    id: int
    ordinal: int = Field(ge=0, le=2)
    query: str = Field(min_length=1, max_length=400)
    status: ResearchQueryStatus
    attempt_count: int = Field(ge=0)
    last_error_code: str | None = None
    evidence_count: int = Field(ge=0)
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class EvidenceCard(StrictModel):
    id: str | None = None
    research_query_id: int | None = None
    is_demo: bool = True
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=1_000)
    source_url: str
    stance: Literal["supports", "opposes", "context"]
    reliability: Literal["high", "medium", "low"]

    @field_validator("source_url")
    @classmethod
    def source_url_must_be_web_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source_url must be an http or https URL")
        return value


class BusinessBaseline(StrictModel):
    """User-provided operating assumptions frozen with a decision."""

    monthly_ticket_volume: int | None = Field(default=None, ge=0, le=10_000_000)
    repetitive_ticket_rate: float | None = Field(default=None, ge=0, le=100)
    average_handle_minutes: float | None = Field(default=None, ge=0, le=1_440)
    loaded_hourly_cost: float | None = Field(default=None, ge=0, le=1_000_000)
    expected_ai_resolution_rate: float | None = Field(default=None, ge=0, le=100)
    review_minutes_per_ai_ticket: float | None = Field(
        default=None, ge=0, le=1_440
    )
    monthly_tool_cost: float | None = Field(default=None, ge=0, le=10_000_000)
    max_acceptable_error_rate: float | None = Field(default=None, ge=0, le=100)


class BaselineAnalysis(StrictModel):
    """Deterministic calculations and collection work derived from a baseline."""

    known_field_count: int = Field(ge=0, le=8)
    total_field_count: int = 8
    is_calculable: bool
    automatable_ticket_volume: float | None = None
    monthly_hours_saved: float | None = None
    estimated_monthly_net_savings: float | None = None
    collection_tasks: list[str] = Field(default_factory=list)
    disclaimer: str = "用户输入试算，不是已验证收益"


class DecisionCreate(StrictModel):
    question: str = Field(min_length=12, max_length=1_000)
    time_window: str = Field(min_length=1, max_length=80)
    budget_limit: int = Field(ge=0, le=10_000_000)
    primary_goal: str = Field(min_length=1, max_length=200)
    business_baseline: BusinessBaseline = Field(default_factory=BusinessBaseline)

    @field_validator("time_window", mode="before")
    @classmethod
    def time_window_must_be_supported(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("time_window must be the supported 14-day window")
        normalized = " ".join(value.split()).casefold()
        if normalized not in {"14 天", "14天", "14 day", "14 days"}:
            raise ValueError("time_window must be the supported 14-day window")
        return "14 天"


class WorkflowEvent(StrictModel):
    stage: str
    status: str
    summary: str
    created_at: datetime


class DecisionSnapshot(StrictModel):
    mode: Literal["demo", "live"] = "demo"
    research_queries: list[ResearchQuery] = Field(default_factory=list)
    failure: dict[str, str] | None = None
    id: str
    question: str
    time_window: str
    budget_limit: int
    primary_goal: str
    business_baseline: BusinessBaseline = Field(default_factory=BusinessBaseline)
    baseline_analysis: BaselineAnalysis
    status: DecisionStatus
    evidence: list[EvidenceCard]
    events: list[WorkflowEvent]
    outputs: dict[str, Any] = Field(default_factory=dict)
    memo: dict[str, Any] | None = None
    review_note: str | None = None


class ReviewRequest(StrictModel):
    action: Literal["accepted", "revised", "deferred"]
    note: str | None = Field(default=None, max_length=1_000)

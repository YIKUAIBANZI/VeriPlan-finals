"""Strict output contracts shared by every model provider."""

from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints, model_validator

from app.schemas import StrictModel


MODEL_STAGES = ("clarifying", "planning", "analyzing", "challenging", "delivering")
TrimmedText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000),
]
QueryText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=400),
]
EvidenceIds = Annotated[list[TrimmedText], Field(max_length=10)]
RequiredEvidenceIds = Annotated[
    list[TrimmedText],
    Field(min_length=1, max_length=10),
]


class ClarifyingOutput(StrictModel):
    summary: TrimmedText
    question: TrimmedText
    time_window: TrimmedText
    budget_limit: int = Field(ge=0, le=10_000_000)
    primary_goal: TrimmedText
    assumptions: list[TrimmedText] = Field(min_length=1, max_length=5)
    questions: list[TrimmedText] = Field(min_length=1, max_length=5)


class PlanningOutput(StrictModel):
    summary: TrimmedText
    queries: list[QueryText] = Field(min_length=2, max_length=5)
    research_questions: list[TrimmedText] = Field(min_length=1, max_length=10)


class AnalysisItem(StrictModel):
    perspective: Literal["增长", "成本", "风险"]
    conclusion: TrimmedText
    evidence_ids: EvidenceIds


class AnalyzingOutput(StrictModel):
    summary: TrimmedText
    analyses: list[AnalysisItem] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def requires_each_perspective_once(self):
        perspectives = {item.perspective for item in self.analyses}
        if perspectives != {"增长", "成本", "风险"}:
            raise ValueError("analyses must contain all three perspectives exactly once")
        return self


class ChallengingOutput(StrictModel):
    summary: TrimmedText
    objection: TrimmedText
    hidden_assumptions: list[TrimmedText] = Field(min_length=1, max_length=5)
    evidence_ids: EvidenceIds


class FactStatement(StrictModel):
    text: TrimmedText
    evidence_ids: RequiredEvidenceIds


class InferenceStatement(StrictModel):
    text: TrimmedText
    evidence_ids: EvidenceIds


class ActionItem(StrictModel):
    days: TrimmedText
    action: TrimmedText
    owner: TrimmedText
    metric: TrimmedText
    stop_condition: TrimmedText
    budget_limit: int = Field(ge=0, le=10_000_000)


class DeliveringOutput(StrictModel):
    summary: TrimmedText
    recommendation: Literal["pilot_before_rollout", "do_not_pilot", "defer"]
    support_score: int = Field(ge=0, le=100)
    score_explanation: TrimmedText
    facts: list[FactStatement] = Field(max_length=10)
    inferences: list[InferenceStatement] = Field(min_length=1, max_length=10)
    objections: list[TrimmedText] = Field(min_length=1, max_length=10)
    action_plan: list[ActionItem] = Field(min_length=1, max_length=5)
    time_window: TrimmedText
    budget_limit: int = Field(ge=0, le=10_000_000)
    primary_goal: TrimmedText
    research_gaps: list[TrimmedText] = Field(max_length=10)


StageOutput = (
    ClarifyingOutput
    | PlanningOutput
    | AnalyzingOutput
    | ChallengingOutput
    | DeliveringOutput
)

_STAGE_MODELS = {
    "clarifying": ClarifyingOutput,
    "planning": PlanningOutput,
    "analyzing": AnalyzingOutput,
    "challenging": ChallengingOutput,
    "delivering": DeliveringOutput,
}


def _require_model(stage: str):
    try:
        return _STAGE_MODELS[stage]
    except KeyError as error:
        raise ValueError(f"Unsupported model stage: {stage}") from error


def stage_schema(stage: str) -> tuple[str, dict[str, Any]]:
    model = _require_model(stage)
    return f"veriplan_{stage}", model.model_json_schema()


def _validate_confirmed_constraints(
    stage: str,
    result: StageOutput,
    context: Mapping[str, Any],
) -> None:
    fields = {
        "clarifying": ("question", "time_window", "budget_limit", "primary_goal"),
        "delivering": ("time_window", "budget_limit", "primary_goal"),
    }.get(stage, ())
    if any(getattr(result, field) != context.get(field) for field in fields):
        raise ValueError("model output changed confirmed constraints")


def _referenced_evidence_ids(stage: str, result: StageOutput) -> set[str]:
    if stage == "analyzing":
        return {item for analysis in result.analyses for item in analysis.evidence_ids}
    if stage == "challenging":
        return set(result.evidence_ids)
    if stage == "delivering":
        statements = [*result.facts, *result.inferences]
        return {item for statement in statements for item in statement.evidence_ids}
    return set()


def _validate_evidence_references(
    stage: str,
    result: StageOutput,
    context: Mapping[str, Any],
) -> None:
    known = {
        str(card["id"])
        for card in context.get("evidence", [])
        if card.get("id") is not None
    }
    unknown = _referenced_evidence_ids(stage, result) - known
    if unknown:
        raise ValueError("model output contains unknown evidence references")


def _validate_action_budget(
    stage: str,
    result: StageOutput,
    context: Mapping[str, Any],
) -> None:
    if stage != "delivering":
        return
    if sum(item.budget_limit for item in result.action_plan) > context["budget_limit"]:
        raise ValueError("action budget exceeds confirmed budget")


def _validate_evidence_gap(
    stage: str,
    result: StageOutput,
    context: Mapping[str, Any],
) -> None:
    if stage != "delivering" or context.get("evidence"):
        return
    if result.facts:
        raise ValueError("facts require evidence")
    if not result.research_gaps:
        raise ValueError("a research gap is required when evidence is missing")


def validate_stage_output(
    stage: str,
    payload: Mapping[str, Any],
    context: Mapping[str, Any],
) -> dict[str, Any]:
    result = _require_model(stage).model_validate(payload)
    _validate_confirmed_constraints(stage, result, context)
    _validate_evidence_references(stage, result, context)
    _validate_action_budget(stage, result, context)
    _validate_evidence_gap(stage, result, context)
    return result.model_dump(mode="json")

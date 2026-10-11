"""Strict output contracts shared by every model provider."""

from collections.abc import Mapping
from copy import deepcopy
from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints, model_validator

from app.schemas import StrictModel


MODEL_STAGES = ("clarifying", "planning", "analyzing", "challenging", "delivering", "ablation")
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


class AblationOutput(StrictModel):
    risks: list[TrimmedText] = Field(min_length=1, max_length=20)


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


COUNCIL_ROLES = ("opportunity", "cfo", "risk")


class MemberOpinion(StrictModel):
    role: Literal["opportunity", "cfo", "risk"]
    stance: Literal["support", "oppose", "conditional"]
    headline: str = Field(min_length=1, max_length=60)
    reasoning: TrimmedText
    key_points: list[TrimmedText] = Field(min_length=1, max_length=4)
    challenged_assumption_ids: list[str] = Field(max_length=8)
    evidence_ids: EvidenceIds
    confidence: int = Field(ge=0, le=100)


class Disagreement(StrictModel):
    stances: dict[str, Literal["support", "oppose", "conditional"]]
    is_split: bool


class AnalyzingOutput(StrictModel):
    summary: TrimmedText
    members: list[MemberOpinion] = Field(min_length=3, max_length=3)
    disagreement: Disagreement

    @model_validator(mode="after")
    def requires_each_role_once(self):
        if {item.role for item in self.members} != set(COUNCIL_ROLES):
            raise ValueError("members must contain all three roles exactly once")
        expected = council_disagreement([item.model_dump() for item in self.members])
        if self.disagreement.model_dump() != expected:
            raise ValueError("disagreement must be computed from member stances")
        return self


def council_disagreement(members):
    stances = {item["role"]: item["stance"] for item in members}
    return {"stances": stances, "is_split": {"support", "oppose"} <= set(stances.values())}


class Objection(StrictModel):
    id: str = Field(pattern=r"^O[1-6]$")
    text: TrimmedText
    severity: Literal["blocker", "major", "minor"]
    targets_assumption_ids: list[str] = Field(max_length=8)
    overlaps_known_risk_index: int | None = Field(ge=0, strict=True)
    evidence_ids: EvidenceIds


class ChallengingOutput(StrictModel):
    summary: TrimmedText
    premortem: TrimmedText
    objections: list[Objection] = Field(min_length=1, max_length=6)
    hidden_assumptions: list[TrimmedText] = Field(min_length=1, max_length=5)


class DeliveryCondition(StrictModel):
    objection_id: str
    condition: TrimmedText


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
    recommendation: Literal["go", "go_with_conditions", "small_test_first", "defer", "no_go"]
    conditions: list[DeliveryCondition] = Field(default_factory=list, max_length=6)
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
    "ablation": AblationOutput,
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


def stage_schema(stage: str, *, member: str | None = None) -> tuple[str, dict[str, Any]]:
    model = MemberOpinion if stage == "analyzing" and member in COUNCIL_ROLES else _require_model(stage)
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
        members = [result] if isinstance(result, MemberOpinion) else result.members
        return {item for member in members for item in member.evidence_ids}
    if stage == "challenging":
        return {ref for item in result.objections for ref in item.evidence_ids}
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
    payload = dict(payload)
    computed = {}
    if stage == "challenging":
        warnings = deepcopy(context.get("calibration_warnings", []))
        novel = sum(item.get("overlaps_known_risk_index") is None for item in payload.get("objections", []) if isinstance(item, dict))
        computed = {"calibration_warnings": warnings, "novel_objection_count": novel}
        for key, value in computed.items():
            if key in payload and payload.pop(key) != value:
                raise ValueError("model changed code-generated calibration or novel count")
    member = context.get("_council_member") if stage == "analyzing" else None
    result = (MemberOpinion if member else _require_model(stage)).model_validate(payload)
    if stage == "analyzing":
        members = [result] if member else result.members
        if member and result.role != member:
            raise ValueError("member role does not match requested role")
        known = {item["id"] for item in context.get("assumptions", []) if "id" in item}
        if any(set(item.challenged_assumption_ids) - known for item in members):
            raise ValueError("unknown assumption reference")
    _validate_confirmed_constraints(stage, result, context)
    _validate_evidence_references(stage, result, context)
    _validate_action_budget(stage, result, context)
    _validate_evidence_gap(stage, result, context)
    if stage == "challenging":
        known = {item["id"] for item in context.get("assumptions", []) if "id" in item}
        objections = result.objections
        if len({item.id for item in objections}) != len(objections):
            raise ValueError("duplicate objection ID")
        for item in objections:
            if set(item.targets_assumption_ids) - known:
                raise ValueError("unknown assumption reference")
            if item.overlaps_known_risk_index is not None and item.overlaps_known_risk_index >= len(context.get("known_risks", [])):
                raise ValueError("unknown known risk index")
            if known and not item.targets_assumption_ids and item.overlaps_known_risk_index is None:
                raise ValueError("objection must target an assumption or known risk")
        for warning in computed["calibration_warnings"]:
            if not any(set(warning["assumption_ids"]) <= set(item.targets_assumption_ids) for item in objections):
                raise ValueError("calibration warning must be covered by an objection")
    if stage == "delivering":
        objections = context.get("outputs", {}).get("challenging", {}).get("objections", [])
        known = {item["id"] for item in objections}
        blockers = {item["id"] for item in objections if item["severity"] == "blocker"}
        conditions = {item.objection_id for item in result.conditions}
        if conditions - known:
            raise ValueError("condition references unknown objection")
        if blockers and (result.recommendation == "go" or not blockers <= conditions):
            raise ValueError("blocker requires a non-go recommendation and covering conditions")
    return result.model_dump(mode="json") | computed

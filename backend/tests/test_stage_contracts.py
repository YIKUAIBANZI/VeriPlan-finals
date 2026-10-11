import pytest
from pydantic import ValidationError

from app.providers.contracts import stage_schema, validate_stage_output
from app.providers.demo import DemoModelProvider, DemoSearchProvider
from tests.test_repository import sample_decision


def context_with_evidence() -> dict:
    context = sample_decision().model_dump(mode="json")
    context["evidence"] = [
        card.model_copy(update={"id": str(index)}).model_dump(mode="json")
        for index, card in enumerate(DemoSearchProvider().search("baseline"), 1)
    ]
    context["outputs"] = {
        "researching": {"research_gaps": ["仍缺少真实数据"]},
        "challenging": {"objection": "证据不足"},
    }
    return context


@pytest.mark.parametrize(
    "stage",
    ["clarifying", "planning", "analyzing", "challenging", "delivering"],
)
def test_demo_outputs_satisfy_shared_contract(stage):
    context = context_with_evidence()
    payload = DemoModelProvider().generate(stage, context)

    assert validate_stage_output(stage, payload, context)["summary"]


def test_contract_overwrites_confirmed_constraint_rewrite():
    context = context_with_evidence()
    payload = DemoModelProvider().generate("clarifying", context)
    payload["budget_limit"] += 1

    assert validate_stage_output("clarifying", payload, context)["budget_limit"] == context["budget_limit"]


def test_contract_rejects_unknown_evidence_reference():
    context = context_with_evidence()
    payload = DemoModelProvider().generate("challenging", context)
    payload["objections"][0]["evidence_ids"] = ["unknown"]

    with pytest.raises(ValueError, match="unknown evidence"):
        validate_stage_output("challenging", payload, context)


def test_delivering_fact_requires_an_existing_citation():
    context = context_with_evidence()
    payload = DemoModelProvider().generate("delivering", context)
    payload["facts"][0]["evidence_ids"] = []

    with pytest.raises(ValidationError):
        validate_stage_output("delivering", payload, context)


def test_delivering_inference_may_be_explicitly_uncited():
    context = context_with_evidence()
    payload = DemoModelProvider().generate("delivering", context)
    payload["inferences"][0]["evidence_ids"] = []

    result = validate_stage_output("delivering", payload, context)

    assert result["inferences"][0]["evidence_ids"] == []


def test_contract_rejects_extra_fields():
    context = context_with_evidence()
    payload = DemoModelProvider().generate("delivering", context)
    payload["extra"] = True

    with pytest.raises(ValidationError):
        validate_stage_output("delivering", payload, context)


def test_contract_rejects_action_budget_overrun():
    context = context_with_evidence()
    payload = DemoModelProvider().generate("delivering", context)
    payload["action_plan"][0]["budget_limit"] = context["budget_limit"] + 1

    with pytest.raises(ValueError, match="action budget"):
        validate_stage_output("delivering", payload, context)


def test_contract_allows_no_facts_but_requires_a_gap_when_no_evidence():
    context = context_with_evidence()
    context["evidence"] = []
    payload = DemoModelProvider().generate("delivering", context)

    assert payload["facts"] == []
    assert validate_stage_output("delivering", payload, context)["research_gaps"]

    payload["research_gaps"] = []
    with pytest.raises(ValueError, match="research gap"):
        validate_stage_output("delivering", payload, context)

    payload["research_gaps"] = ["仍缺少真实数据"]
    payload["facts"] = [{"text": "凭空出现的事实", "evidence_ids": []}]
    with pytest.raises(ValidationError, match="evidence_ids"):
        validate_stage_output("delivering", payload, context)


def test_planning_contract_rejects_duplicates_before_provider_success():
    context = context_with_evidence()
    payload = DemoModelProvider().generate("planning", context)
    payload["queries"] = [payload["queries"][0], payload["queries"][0].upper()]

    with pytest.raises(ValueError, match="distinct queries"):
        validate_stage_output("planning", payload, context)


@pytest.mark.parametrize(
    ("query", "valid"),
    [("q" * 400, True), ("q" * 401, False), ("   ", False)],
)
def test_planning_query_uses_search_storage_limit(query, valid):
    context = context_with_evidence()
    payload = DemoModelProvider().generate("planning", context)
    payload["queries"] = [query, "risk evidence"]

    if valid:
        assert validate_stage_output("planning", payload, context)["queries"][0] == query
    else:
        with pytest.raises(ValidationError):
            validate_stage_output("planning", payload, context)


def test_planning_schema_separates_questions_from_post_research_gaps():
    context = context_with_evidence()
    payload = DemoModelProvider().generate("planning", context)
    _, schema = stage_schema("planning")

    assert "research_questions" in schema["properties"]
    assert "research_gaps" not in schema["properties"]
    assert "research_questions" in payload
    assert "research_gaps" not in payload


def test_contract_requires_each_council_role_once():
    context = context_with_evidence()
    payload = DemoModelProvider().generate("analyzing", context)
    payload["members"][2]["role"] = "opportunity"

    with pytest.raises(ValidationError, match="roles"):
        validate_stage_output("analyzing", payload, context)

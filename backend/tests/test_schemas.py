from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app import schemas
from app.schemas import DecisionCreate, EvidenceCard


def valid_decision_payload(*, time_window="14 天", budget_limit=8000):
    return {
        "question": "Should we pilot AI support before a full rollout?",
        "time_window": time_window,
        "budget_limit": budget_limit,
        "primary_goal": "Reduce repetitive support workload safely",
    }


def test_evidence_card_accepts_only_web_url_stance_and_reliability_enums():
    card = EvidenceCard(
        title="Repeat enquiries are a useful automation starting point",
        summary="A concise paraphrase of source content.",
        source_url="https://example.com/source",
        stance="supports",
        reliability="high",
    )

    assert str(card.source_url) == "https://example.com/source"

    with pytest.raises(ValidationError):
        EvidenceCard(
            title="Unsafe source",
            summary="This should be rejected.",
            source_url="file:///private/secret",
            stance="supports",
            reliability="high",
        )

    with pytest.raises(ValidationError):
        EvidenceCard(
            title="Invalid stance",
            summary="This should be rejected.",
            source_url="https://example.com/source",
            stance="maybe",
            reliability="high",
        )


def test_decision_create_rejects_server_controlled_status_fields():
    with pytest.raises(ValidationError):
        DecisionCreate.model_validate(
            {
                "question": "Should we pilot AI support before a full rollout?",
                "time_window": "14 days",
                "budget_limit": 8000,
                "primary_goal": "Reduce repetitive support workload safely",
                "status": "accepted",
            }
        )


@pytest.mark.parametrize("value", ["14 天", "14天", "14 days", "14 DAY"])
def test_decision_window_normalizes_supported_fourteen_day_aliases(value):
    decision = DecisionCreate.model_validate(
        valid_decision_payload(time_window=value)
    )

    assert decision.time_window == "14 天"


@pytest.mark.parametrize("value", ["3 天", "31 days", "two weeks", ""])
def test_decision_window_rejects_unsupported_or_ambiguous_values(value):
    with pytest.raises(ValidationError, match="supported day"):
        DecisionCreate.model_validate(valid_decision_payload(time_window=value))


def test_supported_window_keeps_zero_budget_valid():
    decision = DecisionCreate.model_validate(
        valid_decision_payload(time_window="14 days", budget_limit=0)
    )

    assert decision.time_window == "14 天"
    assert decision.budget_limit == 0


def test_research_query_contract_and_evidence_provenance():
    query = schemas.ResearchQuery(
        id=7,
        ordinal=0,
        query="AI support workload baseline",
        status=schemas.ResearchQueryStatus.pending,
        attempt_count=0,
        last_error_code=None,
        evidence_count=0,
        created_at=datetime.now(UTC),
        started_at=None,
        finished_at=None,
    )
    evidence = EvidenceCard(
        research_query_id=query.id,
        title="Source",
        summary="Summary",
        source_url="https://example.com/source",
        stance="context",
        reliability="medium",
        is_demo=False,
    )

    assert query.status is schemas.ResearchQueryStatus.pending
    assert evidence.research_query_id == 7

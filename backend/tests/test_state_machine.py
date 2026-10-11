import pytest

from app import schemas
from app import state_machine


def test_state_machine_allows_only_the_next_workflow_stage():
    assert (
        state_machine.transition(schemas.DecisionStatus.draft, schemas.DecisionStatus.clarifying)
        is schemas.DecisionStatus.clarifying
    )

    with pytest.raises(state_machine.InvalidTransition):
        state_machine.transition(schemas.DecisionStatus.draft, schemas.DecisionStatus.delivering)


def test_state_machine_requires_human_review_before_acceptance():
    with pytest.raises(state_machine.InvalidTransition):
        state_machine.transition(schemas.DecisionStatus.delivering, schemas.DecisionStatus.accepted)

    assert (
        state_machine.transition(schemas.DecisionStatus.awaiting_review, schemas.DecisionStatus.accepted)
        is schemas.DecisionStatus.accepted
    )


def test_state_machine_requires_clarification_confirmation_before_research():
    assert (
        state_machine.transition(schemas.DecisionStatus.clarifying, schemas.DecisionStatus.awaiting_confirmation)
        is schemas.DecisionStatus.awaiting_confirmation
    )

    with pytest.raises(state_machine.InvalidTransition):
        state_machine.transition(schemas.DecisionStatus.awaiting_confirmation, schemas.DecisionStatus.researching)

    assert (
        state_machine.transition(schemas.DecisionStatus.awaiting_confirmation, schemas.DecisionStatus.planning)
        is schemas.DecisionStatus.planning
    )

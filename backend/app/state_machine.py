"""Legal state transitions for a VeriPlan decision."""

from app.schemas import DecisionStatus


class InvalidTransition(ValueError):
    """Raised when a caller attempts to skip the controlled workflow."""


_ALLOWED_TRANSITIONS: dict[DecisionStatus, set[DecisionStatus]] = {
    DecisionStatus.draft: {DecisionStatus.clarifying},
    DecisionStatus.clarifying: {DecisionStatus.awaiting_confirmation, DecisionStatus.failed},
    DecisionStatus.awaiting_confirmation: {DecisionStatus.planning},
    DecisionStatus.planning: {DecisionStatus.researching, DecisionStatus.failed},
    DecisionStatus.researching: {DecisionStatus.analyzing, DecisionStatus.failed},
    DecisionStatus.analyzing: {DecisionStatus.challenging, DecisionStatus.failed},
    DecisionStatus.challenging: {DecisionStatus.delivering, DecisionStatus.failed},
    DecisionStatus.delivering: {DecisionStatus.awaiting_review, DecisionStatus.failed},
    DecisionStatus.awaiting_review: {
        DecisionStatus.accepted,
        DecisionStatus.revised,
        DecisionStatus.deferred,
    },
    DecisionStatus.failed: {DecisionStatus.retrying},
    DecisionStatus.retrying: {DecisionStatus.clarifying, DecisionStatus.planning, DecisionStatus.researching, DecisionStatus.analyzing, DecisionStatus.challenging, DecisionStatus.delivering, DecisionStatus.failed},
    DecisionStatus.accepted: set(),
    DecisionStatus.revised: set(),
    DecisionStatus.deferred: set(),
    DecisionStatus.retrospective: set(),
}


def transition(current: DecisionStatus, target: DecisionStatus) -> DecisionStatus:
    """Return the legal target state or refuse to advance the decision."""

    if target not in _ALLOWED_TRANSITIONS[current]:
        raise InvalidTransition(f"Cannot transition from {current.value} to {target.value}")
    return target

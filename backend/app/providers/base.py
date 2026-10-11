from dataclasses import dataclass
from typing import Any, Protocol

from app.schemas import EvidenceCard


class ProviderError(RuntimeError):
    """A stable, redacted provider failure safe to persist by code only."""

    def __init__(self, code: str):
        self.code = code
        self.incomplete_reason = None
        super().__init__(f"External provider failed: {code}")


@dataclass(frozen=True)
class ProviderCallContext:
    decision_id: str
    logical_operation: str
    stage: str | None = None
    research_query_id: int | None = None


class AttemptRecorder(Protocol):
    def start_provider_attempt(
        self,
        *,
        context: ProviderCallContext,
        provider: str,
        attempt_number: int,
    ) -> int: ...

    def finish_provider_attempt(
        self,
        call_id: int,
        *,
        status: str,
        error_code: str | None = None,
        incomplete_reason: str | None = None,
    ) -> None: ...


class ModelProvider(Protocol):
    def generate(
        self,
        stage: str,
        context: dict[str, Any],
        *,
        call_context: ProviderCallContext | None = None,
    ) -> dict[str, Any]: ...


class SearchProvider(Protocol):
    def search(
        self,
        query: str,
        *,
        call_context: ProviderCallContext | None = None,
    ) -> list[EvidenceCard]: ...

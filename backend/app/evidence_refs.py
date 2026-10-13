"""Decision-local display numbers at the prompt/export boundary only."""

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from app.providers.output_validation import ContractViolation


def _map_references(value: Any, resolve: Callable[[Any], Any]) -> Any:
    """Copy JSON data, translating only structured evidence_ids lists."""
    if isinstance(value, Mapping):
        return {
            key: [resolve(ref) for ref in item]
            if key == "evidence_ids" and isinstance(item, list)
            else _map_references(item, resolve)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_map_references(item, resolve) for item in value]
    return value


class EvidenceReferences:
    def __init__(self, evidence_ids: Iterable[str]):
        # Preserve the snapshot's order, including gaps in database IDs.
        self._global_ids = {str(index): str(ref) for index, ref in enumerate(evidence_ids, 1)}
        self._local_ids = {ref: index for index, ref in self._global_ids.items()}

    def local_id(self, evidence_id: str) -> str:
        return self._local_ids.get(str(evidence_id), evidence_id)

    def to_local(self, value: Any) -> Any:
        return _map_references(value, self.local_id)

    def to_global(self, value: Any) -> Any:
        def resolve(ref: Any) -> Any:
            # Leave malformed types to the existing schema validation.
            if not isinstance(ref, str):
                return ref
            ordinal = ref.strip()
            if ordinal not in self._global_ids:
                # Reject before conversion: an out-of-range ordinal may happen
                # to equal a valid global ID and must never pass as that ID.
                raise ContractViolation("evidence_ids", "unknown id", "model output contains unknown evidence references")
            return self._global_ids[ordinal]

        return _map_references(value, resolve)

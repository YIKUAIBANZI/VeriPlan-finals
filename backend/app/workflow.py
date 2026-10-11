"""Persisted stages with explicit human gate and one runner per decision/process."""
from threading import Lock
from typing import Literal

from app.providers.base import (
    ModelProvider,
    ProviderCallContext,
    ProviderError,
    SearchProvider,
)
from app.providers.contracts import validate_stage_output
from app.providers.demo import DemoModelProvider, DemoSearchProvider
from app.providers.search_safety import canonicalize_public_https_url
from app.repository import DecisionRepository
from app.schemas import (
    DecisionSnapshot,
    DecisionStatus,
    EvidenceCard,
    ResearchQueryStatus,
)


def _normalized_evidence_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _canonical_evidence_url(value: str) -> str:
    try:
        return canonicalize_public_https_url(value)
    except ValueError:
        return value.casefold()


def _evidence_identity(card: EvidenceCard) -> tuple[str, tuple[str, str]]:
    return (
        _canonical_evidence_url(card.source_url),
        (
            _normalized_evidence_text(card.title),
            _normalized_evidence_text(card.summary),
        ),
    )


def _normalize_queries(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        query = " ".join(value.split())
        identity = query.casefold()
        if not query or identity in seen:
            continue
        normalized.append(query)
        seen.add(identity)
        if len(normalized) == 3:
            break
    return normalized


def _stable_unique_text(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = " ".join(value.split())
        identity = text.casefold()
        if not text or identity in seen:
            continue
        normalized.append(text)
        seen.add(identity)
    return normalized


class WorkflowEngine:
    _stages = ('clarifying', 'planning', 'researching', 'analyzing', 'challenging', 'delivering')

    def __init__(
        self,
        repository: DecisionRepository,
        model_provider: ModelProvider | None = None,
        search_provider: SearchProvider | None = None,
        *,
        mode: Literal["demo", "live"] = "demo",
    ):
        self._repository = repository
        self._model = model_provider or DemoModelProvider()
        self._search = search_provider or DemoSearchProvider()
        self._mode = mode
        self._lock = Lock()
        self._active: set[str] = set()

    def _require_current_mode(self, snapshot: DecisionSnapshot) -> None:
        if snapshot.mode != self._mode:
            raise ValueError(
                "Decision mode does not match the current application mode"
            )

    def prepare_run(self, decision_id: str, *, retry: bool = False) -> DecisionSnapshot:
        with self._lock:
            snapshot = self._repository.get(decision_id)
            self._require_current_mode(snapshot)
            if decision_id in self._active:
                raise ValueError('Workflow is already running')
            if retry:
                if snapshot.status is not DecisionStatus.failed or not snapshot.failure:
                    raise ValueError('Only a failed stage can be retried')
                self._repository.update_status(decision_id, DecisionStatus.retrying)
            elif snapshot.status is DecisionStatus.draft:
                self._repository.update_status(decision_id, DecisionStatus.clarifying)
            elif snapshot.status is not DecisionStatus.planning:
                raise ValueError(f'Cannot run workflow from {snapshot.status.value}')
            self._active.add(decision_id)
            self._repository.append_event(decision_id, stage='retrying' if retry else self._repository.get(decision_id).status.value, status='queued', summary='演示任务已排队。')
            return self._repository.get(decision_id)

    def run(self, decision_id: str) -> DecisionSnapshot:
        self.prepare_run(decision_id)
        return self.run_prepared(decision_id)

    def retry(self, decision_id: str) -> DecisionSnapshot:
        self.prepare_run(decision_id, retry=True)
        return self.run_prepared(decision_id)

    def run_prepared(self, decision_id: str) -> DecisionSnapshot:
        try:
            snapshot = self._repository.get(decision_id)
            self._require_current_mode(snapshot)
            if snapshot.status is DecisionStatus.retrying:
                self._repository.update_status(decision_id, DecisionStatus(snapshot.failure['stage']))
            while (snapshot := self._repository.get(decision_id)).status.value in self._stages:
                stage = snapshot.status.value
                try:
                    self._repository.append_event(decision_id, stage=stage, status='started', summary=f'演示阶段：{stage}')
                    output = self._run_stage(stage, snapshot)
                    if stage == 'clarifying':
                        target = DecisionStatus.awaiting_confirmation
                    elif stage == 'delivering':
                        target = DecisionStatus.awaiting_review
                    else:
                        target = DecisionStatus(self._stages[self._stages.index(stage) + 1])
                    self._repository.complete_stage(decision_id, stage, output, target)
                except ProviderError as error:
                    self._repository.mark_failed(decision_id, stage, error.code)
                    break
                except Exception:
                    # Raw provider messages may contain credentials or user data.
                    self._repository.mark_failed(decision_id, stage)
                    break
            return self._repository.get(decision_id)
        finally:
            with self._lock:
                self._active.discard(decision_id)

    def confirm_clarification(self, decision_id: str) -> None:
        with self._lock:
            snapshot = self._repository.get(decision_id)
            self._require_current_mode(snapshot)
            if snapshot.status is not DecisionStatus.awaiting_confirmation or decision_id in self._active:
                raise ValueError('Clarification must be awaiting human confirmation')
            self._repository.update_status(decision_id, DecisionStatus.planning)
            self._repository.append_event(decision_id, stage='clarifying', status='confirmed', summary='用户确认目标与约束。')

    def apply_review(
        self,
        decision_id: str,
        *,
        action: str,
        note: str | None = None,
    ) -> None:
        with self._lock:
            snapshot = self._repository.get(decision_id)
            self._require_current_mode(snapshot)
            if decision_id in self._active:
                raise ValueError('Workflow is already running')
            self._repository.apply_review(
                decision_id,
                action=action,
                note=note,
            )

    def recover_interrupted(self) -> None:
        """Called once on application startup; never advance past human gates."""
        self._repository.recover_running_research_queries(self._mode)
        self._repository.recover_open_provider_calls(self._mode)
        for snapshot in self._repository.list():
            if snapshot.mode != self._mode:
                continue
            stage = snapshot.status.value
            if stage == 'retrying' and snapshot.failure:
                self._repository.mark_failed(snapshot.id, snapshot.failure['stage'], 'interrupted')
            elif stage in self._stages:
                # planning without a queued event is a confirmed but unstarted run.
                if stage == 'planning' and not any(event.stage == 'planning' and event.status in {'queued', 'started'} for event in snapshot.events):
                    continue
                self._repository.mark_failed(snapshot.id, stage, 'interrupted')

    def _run_stage(self, stage: str, snapshot: DecisionSnapshot) -> dict:
        if stage == 'researching':
            queries = self._repository.sync_research_queries(
                snapshot.id,
                snapshot.outputs['planning']['queries'],
            )
            persisted = self._repository.get(snapshot.id).evidence
            seen_urls: set[str] = set()
            seen_content: set[tuple[str, str]] = set()
            for existing in persisted:
                url_identity, content_identity = _evidence_identity(existing)
                seen_urls.add(url_identity)
                seen_content.add(content_identity)
            query_gaps: list[str] = []
            for query in queries:
                if query.status is ResearchQueryStatus.succeeded:
                    if query.evidence_count == 0:
                        query_gaps.append(
                            f'查询「{query.query}」未返回可用来源。'
                        )
                    continue
                self._repository.start_research_query(
                    snapshot.id,
                    query.id,
                )
                call_context = ProviderCallContext(
                    decision_id=snapshot.id,
                    logical_operation='researching',
                    stage='researching',
                    research_query_id=query.id,
                )
                try:
                    cards = self._search.search(
                        query.query,
                        call_context=call_context,
                    )
                except ProviderError as error:
                    self._repository.fail_research_query(
                        snapshot.id,
                        query.id,
                        code=error.code,
                    )
                    query_gaps.append(
                        f'查询「{query.query}」未完成（{error.code}）。'
                    )
                    continue
                inserted = 0
                for card in cards:
                    canonical_url, content_identity = _evidence_identity(card)
                    if canonical_url in seen_urls or content_identity in seen_content:
                        continue
                    if canonical_url != card.source_url:
                        card = card.model_copy(update={'source_url': canonical_url})
                    evidence_id = self._repository.save_evidence(
                        snapshot.id,
                        card,
                        research_query_id=query.id,
                    )
                    inserted += int(evidence_id is not None)
                    seen_urls.add(canonical_url)
                    seen_content.add(content_identity)
                self._repository.complete_research_query(
                    snapshot.id,
                    query.id,
                    evidence_count=inserted,
                )
                if inserted == 0:
                    query_gaps.append(
                        f'查询「{query.query}」未返回新增的安全来源。'
                    )
            cards = self._repository.get(snapshot.id).evidence
            if snapshot.mode == 'live' and not cards:
                raise ProviderError('research_no_safe_evidence')
            gaps = list(query_gaps)
            if cards and all(card.is_demo for card in cards):
                gaps.append('只有合成演示材料，没有经过核实的现实证据。')
            if not cards:
                gaps.append('未检索到可用来源。')
            if not cards or (len(cards) == 1 and cards[0].reliability == 'low'):
                gaps.append('缺少足量可信来源。')
            if any(not card.is_demo for card in cards):
                summary = '联网搜索返回的来源摘要已保存，内容仍需人工核验。'
            elif cards:
                summary = '演示研究：合成材料已去重；没有执行真实搜索。'
            else:
                summary = '研究未检索到可用来源；没有生成证据。'
            return {
                'summary': summary,
                'queries': [item.query for item in queries],
                'evidence_ids': [card.id for card in cards],
                'research_gaps': _stable_unique_text(gaps),
            }
        context = snapshot.model_dump(mode='json')
        call_context = ProviderCallContext(
            decision_id=snapshot.id,
            logical_operation=stage,
            stage=stage,
        )
        try:
            output = validate_stage_output(
                stage,
                self._model.generate(
                    stage,
                    context,
                    call_context=call_context,
                ),
                context,
            )
        except ProviderError:
            raise
        except (TypeError, ValueError) as error:
            raise ProviderError('model_invalid_response') from error
        if stage == 'planning':
            output['queries'] = _normalize_queries(output['queries'])
            if len(output['queries']) < 2:
                raise ProviderError('model_invalid_response')
        if stage == 'delivering':
            output['research_gaps'] = _stable_unique_text([
                *snapshot.outputs['researching'].get('research_gaps', []),
                *output.get('research_gaps', []),
            ])
            weak = len(snapshot.evidence) <= 1 and all(card.reliability == 'low' for card in snapshot.evidence)
            was_capped = output['support_score'] > 59
            if output['research_gaps'] or weak:
                output['support_score'] = min(output['support_score'], 59)
                if was_capped:
                    output['score_explanation'] = (
                        output['score_explanation'].rstrip()
                        + ' 存在未解决研究缺口或证据强度不足，'
                        + '支持度按规则上限调整为 59。'
                    )
        return output

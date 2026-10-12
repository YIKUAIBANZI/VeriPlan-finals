"""Persisted stages with explicit human gate and one runner per decision/process."""
from threading import Lock
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import Literal
from app.config import Settings

from app.providers.base import (
    ModelProvider,
    ProviderCallContext,
    ProviderError,
    SearchProvider,
)
from app.providers.contracts import COUNCIL_ROLES, council_disagreement, validate_stage_output
from app.providers.council import EXPERT_LABELS, selected_expert
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
        council_providers: dict[str, ModelProvider] | None = None,
        settings: Settings | None = None,
    ):
        self._repository = repository
        self._model = model_provider or DemoModelProvider()
        self._search = search_provider or DemoSearchProvider()
        self._mode = mode
        self._council_providers = council_providers or {}
        self._settings = settings or Settings()
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
                    self._repository.mark_failed(decision_id, stage, error.code, incomplete_reason=error.incomplete_reason)
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
            return self._run_researching(snapshot)
        context = snapshot.model_dump(mode='json')
        if stage == 'challenging':
            if self._settings.skeptic_input == 'independent':
                context = {key: context[key] for key in (
                    'question', 'time_window', 'budget_limit', 'primary_goal', 'scenario',
                    'horizon_days', 'known_risks', 'assumptions', 'business_baseline',
                    'baseline_analysis', 'evidence',
                )}
                context['outputs'] = {'researching': deepcopy(snapshot.outputs['researching'])}
                context['_skeptic_input'] = 'independent'
            if snapshot.mode == 'demo':
                from app.providers.demo import ensure_demo_calibration_seeds
                with self._lock:
                    ensure_demo_calibration_seeds(self._repository)
            from app.calibration import calibration_profile, calibration_warnings
            context['calibration_warnings'] = calibration_warnings(
                calibration_profile(self._repository.list(), mode=snapshot.mode), snapshot.assumptions,
            )
        if stage == 'analyzing':
            return self._run_council(snapshot, context)
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
            raise ProviderError('model_contract_violation') from error
        if stage == 'challenging' and self._settings.skeptic_review_pass:
            output = self._review_challenge(snapshot, context, output)
        if stage == 'planning':
            output['queries'] = _normalize_queries(output['queries'])
            if len(output['queries']) < 2:
                raise ProviderError('model_contract_violation')
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

    def _run_researching(self, snapshot):
        initial = snapshot.outputs['planning']['queries']
        if self._settings.research_rounds == 1:
            return self._research_round(snapshot, initial)
        followup = snapshot.outputs.get('planning:followup')
        if followup is not None:
            return self._research_round(snapshot, [*initial, *followup['queries']])
        first = self._research_round(snapshot, initial, allow_empty=True)
        context = self._repository.get(snapshot.id).model_dump(mode='json')
        context['outputs'] = {'planning': snapshot.outputs['planning'], 'researching': first}
        context['_research_followup'] = True
        operation = 'planning:followup'
        self._repository.append_event(snapshot.id, stage=operation, status='started', summary='根据首轮证据与缺口规划补充查询。')
        try:
            followup = validate_stage_output('planning', self._model.generate(
                'planning', deepcopy(context), call_context=ProviderCallContext(
                    snapshot.id, operation, stage='researching')), context)
        except (TypeError, ValueError) as error:
            raise ProviderError('model_contract_violation') from error
        # Save the accepted plan before any second-round search; retries reuse it.
        self._repository.save_stage_output(snapshot.id, operation, followup)
        self._repository.append_event(snapshot.id, stage=operation, status='completed', summary='补充查询已保存。')
        return self._research_round(snapshot, [*initial, *followup['queries']], skip_queries=initial)

    def _research_round(self, snapshot, query_texts, *, allow_empty=False, skip_queries=()):
        queries = self._repository.sync_research_queries(
            snapshot.id,
            query_texts,
            max_queries=5 if self._settings.research_rounds == 2 else 3,
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
            if query.query in skip_queries:
                query_gaps.append(f'查询「{query.query}」未完成（{query.last_error_code}）。')
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
        if snapshot.mode == 'live' and not cards and not allow_empty:
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

    def _review_challenge(self, snapshot, context, draft):
        operation = 'challenging:review'
        review_context = deepcopy(context)
        review_context['_challenge_draft'] = deepcopy(draft)
        self._repository.append_event(snapshot.id, stage=operation, status='started', summary='反方开始逐条自审。')
        try:
            reviewed = validate_stage_output('challenging', self._model.generate(
                'challenging', deepcopy(review_context), call_context=ProviderCallContext(
                    snapshot.id, operation, stage='challenging')), review_context)
        except Exception as error:
            # Review quality/transport failures may fall back, but an unavailable
            # audit ledger must still stop execution. Never persist raw errors.
            if isinstance(error, ProviderError) and error.code == 'provider_audit_failed':
                raise
            self._repository.append_event(snapshot.id, stage=operation, status='failed', summary='反方自审未通过，保留已校验首稿。')
            return draft
        self._repository.append_event(snapshot.id, stage=operation, status='completed', summary='反方自审通过，采用审查稿。')
        return reviewed

    def _run_council(self, snapshot: DecisionSnapshot, context: dict) -> dict:
        # Freeze one common input before any worker starts. Each receives its own copy.
        shared = {key: context[key] for key in (
            'question', 'time_window', 'budget_limit', 'primary_goal', 'scenario',
            'horizon_days', 'known_risks', 'assumptions', 'business_baseline',
            'baseline_analysis', 'evidence',
        )}
        shared['outputs'] = {key: context['outputs'][key] for key in ('planning', 'researching') if key in context['outputs']}
        role_labels = {'opportunity': '机会官', 'cfo': '财务官', 'risk': '风险官', 'expert': EXPERT_LABELS[selected_expert(shared)] + '专家'}
        stance_labels = {'support': '支持', 'oppose': '反对', 'conditional': '有条件支持'}

        def generate(role):
            member_context = deepcopy(shared)
            member_context['_council_member'] = role
            self._repository.append_event(snapshot.id, stage=f'council:{role}', status='started', summary=f'{role_labels[role]}：开始独立评估')
            provider = self._council_providers.get(role, self._model)
            operation = ProviderCallContext(decision_id=snapshot.id,
                                            logical_operation=f'analyzing:{role}', stage='analyzing')

            def invoke(selected, call):
                try:
                    return validate_stage_output('analyzing', selected.generate(
                        'analyzing', deepcopy(member_context), call_context=call), member_context)
                except (TypeError, ValueError) as error:
                    raise ProviderError('model_contract_violation') from error

            fallback_from = None
            try:
                opinion = invoke(provider, operation)
            except ProviderError as error:
                # An unavailable audit ledger must never be bypassed via another provider.
                if provider is self._model or error.code == 'provider_audit_failed':
                    raise
                fallback_from = getattr(provider, 'profile', 'custom')
                provider = self._model
                opinion = invoke(provider, replace(operation,
                    logical_operation=operation.logical_operation + ':fallback', single_attempt=True))
            opinion['model_label'] = getattr(provider, 'model_label', '自定义模型')
            if fallback_from:
                opinion['fallback_from'] = fallback_from
            self._repository.append_event(snapshot.id, stage=f'council:{role}', status='completed', summary=f"{role_labels[role]}：{stance_labels[opinion['stance']]}——{opinion['headline']}")
            return opinion

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(generate, role) for role in COUNCIL_ROLES]
            members = [future.result() for future in futures]
        return validate_stage_output('analyzing', {
            'summary': '四位委员已完成独立评估。',
            'members': members, 'disagreement': council_disagreement(members),
        }, context)

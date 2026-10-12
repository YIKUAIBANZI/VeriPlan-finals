"""Offline acceptance for the opt-in depth switches."""
from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app
from app.providers.demo import DemoModelProvider, DemoSearchProvider
from app.providers.prompts import build_prompt
from app.repository import DecisionRepository
from app.schemas import DecisionCreate
from app.workflow import WorkflowEngine
from tests.test_finals_scenarios import general_payload
from tests.test_stage_contracts import context_with_evidence


def run_decision(repo, engine, *, mode='demo'):
    row = repo.create(DecisionCreate(**general_payload()), mode=mode)
    assert engine.run(row.id).status == 'awaiting_confirmation'
    engine.confirm_clarification(row.id)
    return engine.run(row.id)


def test_skeptic_input_configuration(monkeypatch):
    assert Settings().skeptic_input == 'council'
    monkeypatch.setenv('SKEPTIC_INPUT', 'independent')
    assert Settings().skeptic_input == 'independent'
    with pytest.raises(ValidationError):
        Settings(skeptic_input='unknown')


@pytest.mark.parametrize('independent', [False, True])
def test_skeptic_prompt_excludes_council_only_when_independent(independent):
    context = context_with_evidence()
    context['outputs']['analyzing'] = {'summary': 'COUNCIL_SENTINEL'}
    context['_skeptic_input'] = 'independent' if independent else 'council'
    original = deepcopy(context)
    _, prompt = build_prompt('challenging', context)
    selected = json.loads(prompt)['context']
    assert ('COUNCIL_SENTINEL' in prompt) is (not independent)
    if independent:
        assert 'analysis' not in selected
        assert selected['research'] == context['outputs']['researching']
    assert context == original


def test_application_passes_independent_context_but_delivery_keeps_both(tmp_path):
    seen = {}

    class Model(DemoModelProvider):
        def generate(self, stage, context, *, call_context=None):
            if stage in {'challenging', 'delivering'}:
                seen[stage] = deepcopy(context)
            return super().generate(stage, context, call_context=call_context)

    app = create_app(tmp_path / 'db', settings=Settings(app_mode='live', enable_live_workflow=True,
        deepseek_api_key='fake', tavily_api_key='fake', skeptic_input='independent'),
        model_provider=Model(), search_provider=DemoSearchProvider())
    result = run_decision(app.state.repository, app.state.workflow, mode='live')
    assert result.status == 'awaiting_review', result.failure
    assert set(seen['challenging']['outputs']) == {'researching'}
    assert not {'events', 'memo', 'failure', 'review_note'} & seen['challenging'].keys()
    assert {'analyzing', 'challenging'} <= seen['delivering']['outputs'].keys()


@pytest.mark.parametrize('global_effort', ['low', 'medium', 'high'])
def test_reasoning_effort_environment_reaches_default_and_mapped_requests(tmp_path, monkeypatch, global_effort):
    import httpx2
    from tests.test_council_models import mock_factories, live_settings
    from tests.test_live_hardening import decode_stage_context, envelope

    monkeypatch.setenv('DEEPSEEK_REASONING_EFFORT', global_effort)
    monkeypatch.setenv('REASONING_EFFORT_STAGES', 'challenging:high,delivering:medium')
    seen = []

    def handler(request):
        body = json.loads(request.content)
        stage, context, message = decode_stage_context('deepseek', request)
        seen.append((stage, body['reasoning']['effort']))
        if stage == 'challenging' and 'repair_errors' not in message:
            return envelope('deepseek', {})
        return envelope('deepseek', DemoModelProvider().generate(stage, context))

    mock_factories(monkeypatch, handler)
    settings = live_settings(council_model_map='expert=deepseek:other-model')
    app = create_app(tmp_path / 'db', settings=settings, search_provider=DemoSearchProvider())
    try:
        result = run_decision(app.state.repository, app.state.workflow, mode='live')
    finally:
        app.state.workflow._model.close()
        app.state.workflow._council_providers['expert'].close()
    assert result.status == 'awaiting_review', result.failure
    assert len(seen) == 9
    assert all(effort == {'challenging': 'high', 'delivering': 'medium'}.get(stage, global_effort)
               for stage, effort in seen)


@pytest.mark.parametrize('updates', [
    {'deepseek_reasoning_effort': 'max'},
    {'reasoning_effort_stages': 'unknown:high'},
    {'reasoning_effort_stages': 'challenging:max'},
    {'reasoning_effort_stages': 'challenging:high,challenging:low'},
    {'reasoning_effort_stages': 'challenging=high'},
    {'reasoning_effort_stages': 'challenging:high,'},
])
def test_invalid_effort_configuration_is_rejected(updates):
    with pytest.raises(ValidationError):
        Settings(**updates)


@pytest.mark.parametrize('adapter', ['deepseek', 'compat'])
@pytest.mark.parametrize('outcome', ['success', 'repair', 'failure'])
def test_review_validates_repairs_and_preserves_calibration(tmp_path, adapter, outcome):
    from tests.test_live_hardening import build_adapter, decode_stage_context, envelope
    repo = DecisionRepository(tmp_path / 'db')
    seen = []

    def handler(request):
        stage, context, message = decode_stage_context(adapter, request)
        draft = context.get('challenge_draft')
        output = DemoModelProvider().generate(stage, context)
        if draft is not None:
            seen.append(message)
            assert draft['summary'] == '演示反方：关键收益尚未证实。'
            assert 'analysis' not in context  # D1 remains in force during review/repair.
            assert context['calibration_warnings']
            output['summary'] = '审查后的反方意见'
            output['objections'][0]['overlaps_known_risk_index'] = 0
            output.pop('novel_objection_count')  # Code must recompute it for the final draft.
            if outcome == 'failure' or (outcome == 'repair' and 'repair_errors' not in message):
                output['objections'][0]['targets_assumption_ids'] = []
                # Still targets a known risk, but fails the full warning coverage rule.
        return envelope(adapter, output)

    model = build_adapter(adapter, handler, repo)
    engine = WorkflowEngine(repo, model_provider=model, settings=Settings(
        skeptic_input='independent', skeptic_review_pass=True))
    try:
        result = run_decision(repo, engine)
    finally:
        model.close()
    assert result.status == 'awaiting_review', result.failure
    assert len(seen) == (1 if outcome == 'success' else 2)
    challenge = result.outputs['challenging']
    assert challenge['summary'] == ('演示反方：关键收益尚未证实。' if outcome == 'failure' else '审查后的反方意见')
    assert challenge['novel_objection_count'] == (1 if outcome == 'failure' else 0)
    assert challenge['calibration_warnings'] == seen[0]['context']['calibration_warnings']
    assert result.memo['conditions'][0]['objection_id'] == 'O1'
    calls = [c for c in repo.list_provider_calls(result.id) if c['logical_operation'].startswith('challenging:review')]
    assert [c['logical_operation'] for c in calls] == (['challenging:review'] if outcome == 'success' else
        ['challenging:review', 'challenging:review:repair'])
    assert all(c['status'] != 'running' for c in calls)
    events = [e.status for e in result.events if e.stage == 'challenging:review']
    assert events == ['started', 'failed' if outcome == 'failure' else 'completed']


@pytest.mark.parametrize('failure', ['exception', 'audit'])
def test_review_failure_cannot_mutate_first_draft_or_leak_errors(tmp_path, failure):
    from app.providers.base import ProviderError

    class Model(DemoModelProvider):
        def generate(self, stage, context, *, call_context=None):
            if call_context.logical_operation == 'challenging:review':
                context['_challenge_draft']['summary'] = 'private-secret'
                context['calibration_warnings'].clear()
                if failure == 'audit':
                    raise ProviderError('provider_audit_failed')
                raise RuntimeError('private-secret')
            return super().generate(stage, context, call_context=call_context)

    repo = DecisionRepository(tmp_path / 'db')
    engine = WorkflowEngine(repo, model_provider=Model(), settings=Settings(skeptic_review_pass=True))
    result = run_decision(repo, engine)
    assert 'private-secret' not in result.model_dump_json()
    if failure == 'audit':
        assert result.failure['code'] == 'provider_audit_failed'
    else:
        assert result.status == 'awaiting_review'
        assert result.outputs['challenging']['calibration_warnings']
        assert any(e.stage == 'challenging:review' and e.status == 'failed' for e in result.events)


def test_review_prompt_and_environment_flag(monkeypatch):
    assert Settings().skeptic_review_pass is False
    monkeypatch.setenv('SKEPTIC_REVIEW_PASS', 'true')
    assert Settings().skeptic_review_pass is True
    context = context_with_evidence()
    context['_challenge_draft'] = DemoModelProvider().generate('challenging', context)
    instructions, prompt = build_prompt('challenging', context)
    assert json.loads(prompt)['context']['challenge_draft'] == context['_challenge_draft']
    assert all(word in instructions for word in ('逐条审查', '可核验条件', '阻断性风险', '最多 6 条'))


def test_two_rounds_execute_five_queries_and_deduplicate_evidence(tmp_path):
    from tests.test_provider_boundaries import real_evidence
    calls, followups = [], []

    class Model(DemoModelProvider):
        def generate(self, stage, context, *, call_context=None):
            if call_context.logical_operation == 'planning:followup':
                followups.append(deepcopy(context))
                return {'queries': ['additional cost', 'additional risk']}
            output = super().generate(stage, context, call_context=call_context)
            if stage == 'planning':
                output['queries'] = ['baseline', 'risk', 'cost', 'ignored fourth', 'ignored fifth']
            return output

    class Search:
        def search(self, query, *, call_context=None):
            calls.append(query)
            if query.startswith('additional'):
                return [real_evidence('duplicate', 'same url', 'https://source.example/baseline?utm_source=x'),
                        real_evidence(' RISK ', 'Finding risk', 'https://mirror.example/risk'),
                        real_evidence(query, query, 'https://source.example/' + query.replace(' ', '-'))]
            return [real_evidence(query, 'Finding ' + query, 'https://source.example/' + query)]

    repo = DecisionRepository(tmp_path / 'db')
    engine = WorkflowEngine(repo, model_provider=Model(), search_provider=Search(), settings=Settings(research_rounds=2))
    result = run_decision(repo, engine)
    assert result.status == 'awaiting_review', result.failure
    assert calls == ['baseline', 'risk', 'cost', 'additional cost', 'additional risk']
    assert len(result.evidence) == 5
    assert len(followups) == 1 and len(followups[0]['evidence']) == 3
    assert followups[0]['outputs']['researching']['research_gaps'] == []
    assert result.outputs['planning:followup']['queries'] == calls[-2:]
    assert result.outputs['researching']['queries'] == calls
    assert all(q.status == 'succeeded' for q in result.research_queries)
    assert all(card.research_query_id for card in result.evidence)


@pytest.mark.parametrize('interrupt_at', [3, 4])
def test_followup_plan_survives_restart_without_replanning_or_repeating_successes(tmp_path, interrupt_at):
    calls = []

    class Search(DemoSearchProvider):
        interrupted = False
        def search(self, query, *, call_context=None):
            calls.append(query)
            if len(calls) == interrupt_at and not self.interrupted:
                self.interrupted = True
                raise RuntimeError('private-interruption')
            return super().search(query, call_context=call_context)

    class Model(DemoModelProvider):
        followups = 0
        def generate(self, stage, context, *, call_context=None):
            if call_context.logical_operation == 'planning:followup':
                self.followups += 1
            return super().generate(stage, context, call_context=call_context)

    path = tmp_path / 'db'
    repo, model, search = DecisionRepository(path), Model(), Search()
    engine = WorkflowEngine(repo, model_provider=model, search_provider=search, settings=Settings(research_rounds=2))
    failed = run_decision(repo, engine)
    assert failed.status == 'failed' and failed.failure['stage'] == 'researching'
    assert 'planning:followup' in failed.outputs
    assert 'private-interruption' not in failed.model_dump_json()
    repo._engine.dispose()
    repo = DecisionRepository(path)
    restarted = WorkflowEngine(repo, model_provider=model, search_provider=search, settings=Settings(research_rounds=2))
    restarted.recover_interrupted()
    result = restarted.retry(failed.id)
    assert result.status == 'awaiting_review', result.failure
    assert model.followups == 1
    assert calls.count(calls[0]) == calls.count(calls[1]) == 1
    assert calls.count(calls[interrupt_at - 1]) == 2
    assert len(result.evidence) > 3 and all(card.is_demo for card in result.evidence)


def test_research_rounds_environment_and_repository_limits(tmp_path, monkeypatch):
    assert Settings().research_rounds == 1
    monkeypatch.setenv('RESEARCH_ROUNDS', '2')
    assert Settings().research_rounds == 2
    for value in (0, 3, 'invalid'):
        with pytest.raises(ValidationError):
            Settings(research_rounds=value)
    repo = DecisionRepository(tmp_path / 'db')
    row = repo.create(DecisionCreate(**general_payload()))
    initial = repo.sync_research_queries(row.id, ['one', 'two', 'three'])
    with pytest.raises(ValueError):
        repo.sync_research_queries(row.id, ['one', 'two', 'three', 'four'])
    extended = repo.sync_research_queries(row.id, ['one', 'two', 'three', 'four', 'five'], max_queries=5)
    assert [q.id for q in extended[:3]] == [q.id for q in initial]
    for queries in (['one', 'two', 'three', 'four', 'five', 'six'], ['changed', 'two', 'three']):
        with pytest.raises(ValueError):
            repo.sync_research_queries(row.id, queries, max_queries=5)


@pytest.mark.parametrize('queries', [[], ['one', 'two', 'three'], ['x' * 401], ['  '], ['baseline'], ['extra', ' EXTRA ']])
def test_followup_contract_rejects_unbounded_or_repeated_queries(queries):
    from app.providers.contracts import validate_stage_output
    context = context_with_evidence() | {'_research_followup': True}
    context['outputs']['planning'] = {'queries': ['baseline', 'risk']}
    with pytest.raises(ValueError):
        validate_stage_output('planning', {'queries': queries}, context)


@pytest.mark.parametrize('adapter', ['deepseek', 'compat'])
def test_followup_small_schema_prompt_and_single_repair(adapter):
    from tests.test_live_hardening import build_adapter, input_data, envelope
    from tests.test_deepseek_provider import AttemptSpy
    from app.providers.base import ProviderCallContext
    context = context_with_evidence() | {'_research_followup': True}
    context['outputs']['planning'] = {'queries': ['baseline', 'risk']}
    context['outputs']['analyzing'] = {'summary': 'COUNCIL_PRIVATE'}
    seen, spy = [], AttemptSpy()

    def handler(request):
        body = json.loads(request.content)
        schema = body['text']['format']['schema'] if adapter == 'deepseek' else body['response_format']['json_schema']['schema']
        assert set(schema['properties']) == {'queries'}
        assert schema['properties']['queries']['maxItems'] == 2
        message = input_data(adapter, request)
        seen.append(message)
        assert message['context']['research_gaps'] == context['outputs']['researching']['research_gaps']
        assert message['context']['evidence']
        assert 'COUNCIL_PRIVATE' not in json.dumps(message)
        return envelope(adapter, {'queries': ['baseline']} if len(seen) == 1 else {'queries': ['extra check']})

    model = build_adapter(adapter, handler, spy)
    try:
        output = model.generate('planning', context, call_context=ProviderCallContext('id', 'planning:followup', stage='researching'))
    finally:
        model.close()
    assert output == {'queries': ['extra check']}
    assert len(seen) == 2
    assert [c[0].logical_operation for c in spy.started] == ['planning:followup', 'planning:followup:repair']


@pytest.mark.parametrize('rescued', [False, True])
def test_second_round_can_rescue_empty_live_research_but_never_invents_evidence(tmp_path, rescued):
    from app.providers.base import ProviderError
    from tests.test_provider_boundaries import real_evidence
    calls = []

    class Search:
        def search(self, query, *, call_context=None):
            calls.append(query)
            if not query.startswith('veriplan followup '):
                raise ProviderError('search_timeout')
            if rescued:
                return [real_evidence('source', 'source summary', 'https://source.example/report')]
            return []

    repo = DecisionRepository(tmp_path / 'db')
    engine = WorkflowEngine(repo, search_provider=Search(), mode='live', settings=Settings(research_rounds=2))
    result = run_decision(repo, engine, mode='live')
    assert len(calls) == 4  # Failed first-round queries are not retried in round two.
    if rescued:
        assert result.status == 'awaiting_review'
        assert len(result.evidence) == 1 and not result.evidence[0].is_demo
        assert any('search_timeout' in gap for gap in result.memo['research_gaps'])
        assert result.memo['support_score'] <= 59
    else:
        assert result.failure['code'] == 'research_no_safe_evidence'
        assert result.evidence == [] and result.memo is None


def test_followup_contract_accepts_one_query_and_anthropic_uses_small_schema():
    from tests.test_anthropic_provider import _FakeClient, _text, _provider
    context = context_with_evidence() | {'_research_followup': True}
    client = _FakeClient([_text({'queries': ['extra check']})])
    assert _provider(client).generate('planning', context) == {'queries': ['extra check']}
    schema = client.calls[0]['output_config']['format']['schema']
    assert set(schema['properties']) == {'queries'}
    assert schema['properties']['queries']['minItems'] == 1


def test_b_only_uses_environment_switches_and_never_calls_other_arms(tmp_path, monkeypatch):
    import csv
    from tests.test_finals_delivery import load_script
    monkeypatch.setenv('SKEPTIC_INPUT', 'independent')
    monkeypatch.setenv('SKEPTIC_REVIEW_PASS', 'true')
    monkeypatch.setenv('RESEARCH_ROUNDS', '2')
    calls = []

    class Model(DemoModelProvider):
        def generate(self, stage, context, *, call_context=None):
            calls.append(call_context.logical_operation)
            assert stage != 'ablation'
            if stage == 'challenging':
                assert 'analyzing' not in context['outputs']
            return super().generate(stage, context, call_context=call_context)

    result = load_script('ablation').run_ablation([{'question_id': 'Q1'} | general_payload()],
        output_dir=tmp_path, model_provider=Model(), b_only=True)
    assert result['failed'] == [] and set(result['risk_counts']) == {'B'}
    assert len(calls) == 10
    assert 'planning:followup' in calls and 'challenging:review' in calls
    rows = list(csv.DictReader((tmp_path / 'risks.csv').open()))
    assert {row['arm'] for row in rows} == {'B'} and all(row['label'] == '' for row in rows)
    summary = (tmp_path / 'summary.md').read_text()
    assert '仅 B 臂' in summary and 'independent' in summary
    assert '| A ' not in summary and '| C ' not in summary and '| D ' not in summary


def test_b_only_cli_and_live_authorization_are_preserved(tmp_path):
    import subprocess
    import sys
    from tests.test_finals_delivery import ROOT
    path = tmp_path / 'questions.jsonl'
    path.write_text(json.dumps({'question_id': 'Q1'} | general_payload()) + '\n')
    command = [sys.executable, str(ROOT / 'scripts/ablation.py'), '--input', str(path),
               '--output-dir', str(tmp_path / 'out'), '--b-only']
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert set(json.loads(result.stdout)['risk_counts']) == {'B'}
    refused = subprocess.run(command + ['--live'], capture_output=True, text=True)
    assert refused.returncode != 0 and '--i-authorize-live' in refused.stderr


def test_b_only_live_mock_routes_all_depth_settings_from_environment(tmp_path, monkeypatch):
    from tests.test_council_models import mock_factories
    from tests.test_live_hardening import decode_stage_context, envelope
    from tests.test_finals_delivery import load_script
    for key, value in {'APP_MODE': 'live', 'ENABLE_LIVE_WORKFLOW': 'true',
        'DEEPSEEK_API_KEY': 'fake-private-key', 'TAVILY_API_KEY': 'fake-private-search',
        'SKEPTIC_INPUT': 'independent', 'SKEPTIC_REVIEW_PASS': 'true', 'RESEARCH_ROUNDS': '2',
        'DEEPSEEK_REASONING_EFFORT': 'medium', 'REASONING_EFFORT_STAGES': 'challenging:high'}.items():
        monkeypatch.setenv(key, value)
    seen = []

    def handler(request):
        body = json.loads(request.content)
        stage, context, message = decode_stage_context('deepseek', request)
        followup = body['text']['format']['name'] == 'veriplan_planning_followup'
        if followup:
            context['_research_followup'] = True
        if stage == 'challenging':
            assert 'analysis' not in message['context']
        seen.append((stage, body['reasoning']['effort'], followup, 'challenge_draft' in context))
        return envelope('deepseek', DemoModelProvider().generate(stage, context))

    mock_factories(monkeypatch, handler)
    result = load_script('ablation').run_ablation([{'question_id': 'Q1'} | general_payload()],
        output_dir=tmp_path, mode='live', authorized=True, b_only=True, search_provider=DemoSearchProvider())
    assert result['failed'] == [] and result['risk_counts']['B'] > 0
    assert len(seen) == 10 and all(stage != 'ablation' for stage, *_ in seen)
    assert sum(followup for _, _, followup, _ in seen) == 1
    assert sum(review for _, _, _, review in seen) == 1
    assert all(effort == ('high' if stage == 'challenging' else 'medium') for stage, effort, *_ in seen)
    assert 'fake-private' not in repr(result) + (tmp_path / 'summary.md').read_text()

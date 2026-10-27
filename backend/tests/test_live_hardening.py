"""Offline regressions for the Live hardening contract."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from tests.helpers import login

from app.config import Settings
from app.main import create_app
from app.providers.contracts import validate_stage_output
from app.providers.demo import DemoModelProvider, DemoSearchProvider
from tests.test_finals_scenarios import general_payload
from tests.test_stage_contracts import context_with_evidence


@pytest.mark.parametrize('stage', ['clarifying', 'delivering'])
@pytest.mark.parametrize('replacement', ['MODEL-REWRITE', None, {'invalid': True}])
def test_confirmed_fields_are_injected_before_parsing(stage, replacement):
    context = context_with_evidence()
    payload = DemoModelProvider().generate(stage, context)
    fields = ['time_window', 'budget_limit', 'primary_goal']
    if stage == 'clarifying':
        fields.append('question')
    for field in fields:
        payload[field] = replacement
    original = deepcopy(payload)
    result = validate_stage_output(stage, payload, context)
    assert all(result[field] == context[field] for field in fields)
    assert payload == original  # Do not mutate the provider's input.
    for field in fields:
        del payload[field]
    result = validate_stage_output(stage, payload, context)
    assert all(result[field] == context[field] for field in fields)


def test_rewritten_constraints_never_reach_snapshot_or_export(tmp_path):
    class RewritingModel(DemoModelProvider):
        def generate(self, stage, context, *, call_context=None):
            output = super().generate(stage, context, call_context=call_context)
            if stage in ('clarifying', 'delivering'):
                for field in ('question', 'time_window', 'budget_limit', 'primary_goal'):
                    if field in output:
                        output[field] = 'MODEL-REWRITE'
            return output

    with TestClient(create_app(tmp_path / 'db', settings=Settings(app_mode='live', enable_live_workflow=True, deepseek_api_key='fake', tavily_api_key='fake'), model_provider=RewritingModel(), search_provider=DemoSearchProvider())) as client:
        login(client)
        created = client.post('/api/decisions', json=general_payload()).json()
        url = '/api/decisions/' + created['id']
        client.post(url + '/run')
        assert client.get(url).json()['status'] == 'awaiting_confirmation'
        client.post(url + '/confirm')
        client.post(url + '/run')
        snapshot = client.get(url)
        assert snapshot.json()['status'] == 'awaiting_review'
        assert 'MODEL-REWRITE' not in snapshot.text
        for stage in ('clarifying', 'delivering'):
            for field in ('time_window', 'budget_limit', 'primary_goal'):
                assert snapshot.json()['outputs'][stage][field] == created[field]
        client.post(url + '/review', json={'action': 'deferred'})
        exported = client.get(url + '/export.md')
        assert exported.status_code == 200
        assert 'MODEL-REWRITE' not in exported.text

import json
import httpx2
from app.providers.base import ProviderCallContext, ProviderError
from tests.test_deepseek_provider import make_provider, completed_response, AttemptSpy
from tests.test_openai_compat import provider as compat_provider, response as compat_response


@pytest.fixture(params=['deepseek', 'compat'])
def adapter(request):
    return request.param


def envelope(adapter, payload):
    return httpx2.Response(200, json=completed_response(payload)) if adapter == 'deepseek' else compat_response(payload)


def build_adapter(adapter, handler, recorder=None):
    return (make_provider if adapter == 'deepseek' else compat_provider)(handler, recorder=recorder)


def input_data(adapter, request):
    body = json.loads(request.content)
    return json.loads(body['input'] if adapter == 'deepseek' else body['messages'][1]['content'])


@pytest.mark.parametrize('fault', ['json', 'schema', 'extra', 'reference', 'blocker', 'computed', 'queries'])
def test_one_repair_is_redacted_audited_and_validated(adapter, fault):
    context = context_with_evidence()
    context['assumptions'] = [{'id': 'A1'}]
    stage = 'challenging'
    if fault == 'blocker':
        stage = 'delivering'
        context['outputs']['challenging'] = {'objections': [{'id': 'O1', 'severity': 'blocker', 'text': '阻断风险'}]}
    if fault == 'queries':
        stage = 'planning'
    valid = DemoModelProvider().generate(stage, context)
    broken = deepcopy(valid)
    if fault == 'schema': broken['summary'] = None
    if fault == 'extra': broken['secret-extra-key'] = 'unit-secret'
    if fault == 'reference': broken['objections'][0]['targets_assumption_ids'] = ['unit-secret']
    if fault == 'blocker': broken['conditions'] = []
    if fault == 'computed': broken['novel_objection_count'] = 999
    if fault == 'queries': broken['queries'] = ['baseline', ' BASELINE ']
    requests, spy = [], AttemptSpy()
    def handler(request):
        requests.append(input_data(adapter, request))
        if len(requests) == 1 and fault == 'json':
            response = envelope(adapter, valid).json()
            if adapter == 'deepseek': response['output'][1]['content'][0]['text'] = 'unit-secret bad json'
            else: response['choices'][0]['message']['content'] = 'unit-secret bad json'
            return httpx2.Response(200, json=response)
        return envelope(adapter, broken if len(requests) == 1 else valid)
    model = build_adapter(adapter, handler, spy)
    try:
        result = model.generate(stage, context, call_context=ProviderCallContext('id', stage))
    finally:
        model.close()
    assert result == validate_stage_output(stage, valid, context)
    assert len(requests) == 2
    repair = requests[1]['repair_errors']
    assert repair and 'unit-secret' not in repr(repair) and 'secret-extra-key' not in repr(repair)
    if fault == 'reference': assert repair == ['objections[0].targets_assumption_ids: unknown id']
    assert [call[0].logical_operation for call in spy.started] == [stage, stage + ':repair']
    assert spy.finished == [(1, 'failed', 'model_invalid_json' if fault == 'json' else 'model_contract_violation'), (2, 'succeeded', None)]


@pytest.mark.parametrize('fault,code', [('json', 'model_invalid_json'), ('schema', 'model_contract_violation'), ('incomplete', 'model_incomplete')])
def test_two_failures_are_bounded_with_specific_code(adapter, fault, code):
    requests, spy = [], AttemptSpy()
    def handler(request):
        requests.append(input_data(adapter, request))
        if fault == 'json': return httpx2.Response(200, content='unit-secret non-json-envelope')
        body = envelope(adapter, {'summary': 'unit-secret'}).json()
        if fault == 'incomplete':
            if adapter == 'deepseek': body.update(status='incomplete', incomplete_details={'reason': 'max_output_tokens'})
            else: body['choices'][0]['finish_reason'] = 'length'
        return httpx2.Response(200, json=body)
    model = build_adapter(adapter, handler, spy)
    try:
        with pytest.raises(ProviderError) as exc:
            model.generate('clarifying', context_with_evidence(), call_context=ProviderCallContext('id', 'clarifying'))
        assert exc.value.code == code
        if fault == 'incomplete': assert exc.value.incomplete_reason == 'max_output_tokens'
        assert 'unit-secret' not in str(exc.value)
    finally:
        model.close()
    assert len(requests) == 2
    assert len(spy.finished) == 2 and all(call[1:3] == ('failed', code) for call in spy.finished)
    assert 'unit-secret' not in repr(spy.__dict__) + repr(requests[1]['repair_errors'])

from collections import Counter
from threading import Barrier, Lock
from app.repository import DecisionRepository
from app.schemas import DecisionCreate
from app.workflow import WorkflowEngine


def decode_stage_context(adapter, request):
    message = input_data(adapter, request)
    stage, context = message['stage'], message['context']
    context.setdefault('evidence', [])
    context['outputs'] = {'planning': context.get('planning', {}), 'researching': context.get('research', {}), 'challenging': context.get('challenge', {})}
    if stage == 'analyzing':
        body = json.loads(request.content)
        instructions = body['instructions'] if adapter == 'deepseek' else body['messages'][0]['content']
        context['_council_member'] = next(role for role in ('opportunity', 'cfo', 'risk', 'expert') if f'本次独立席位 {role}' in instructions)
    return stage, context, message


@pytest.mark.parametrize('fails_twice', [False, True])
def test_council_repairs_are_independent_parallel_and_never_save_partial_output(adapter, tmp_path, fails_twice):
    repo = DecisionRepository(tmp_path / 'council.db')
    counts, seen, lock, barrier = Counter(), [], Lock(), Barrier(4)
    def handler(request):
        stage, context, message = decode_stage_context(adapter, request)
        role = context.get('_council_member')
        with lock:
            counts[role or stage] += 1
            n = counts[role or stage]
            seen.append(message)
        if role and n == 1: barrier.wait(timeout=5)  # All original seats must overlap.
        output = DemoModelProvider().generate(stage, context)
        if role == 'cfo' and (n == 1 or fails_twice): output['evidence_ids'] = ['secret-fake-id']
        return envelope(adapter, output)
    model = build_adapter(adapter, handler, repo)
    decision = repo.create(DecisionCreate(**general_payload()), mode='live')
    engine = WorkflowEngine(repo, model_provider=model, search_provider=DemoSearchProvider(), mode='live')
    try:
        assert engine.run(decision.id).status == 'awaiting_confirmation'
        engine.confirm_clarification(decision.id)
        result = engine.run(decision.id)
    finally: model.close()
    assert counts['opportunity'] == counts['risk'] == counts['expert'] == 1 and counts['cfo'] == 2
    calls = repo.list_provider_calls(decision.id)
    assert [c['logical_operation'] for c in calls if c['logical_operation'].endswith(':repair')] == ['analyzing:cfo:repair']
    assert all(c['status'] != 'running' for c in calls)
    assert 'secret-fake-id' not in repr(calls) + result.model_dump_json()
    for message in seen:
        if message['stage'] == 'analyzing':
            assert 'analysis' not in message['context'] and 'members' not in message['context']
    if fails_twice:
        assert result.status == 'failed' and result.failure['code'] == 'model_contract_violation'
        assert 'analyzing' not in result.outputs and result.memo is None
        assert counts['challenging'] == counts['delivering'] == 0
    else:
        assert result.status == 'awaiting_review'
        assert result.memo['support_score'] <= 59


@pytest.mark.parametrize('reason,expected', [('max_output_tokens', 'max_output_tokens'), ('content_filter', 'content_filter'), ('unit-secret', 'unknown'), ({'raw': 'unit-secret'}, 'unknown')])
def test_incomplete_reason_is_allowlisted_in_ledger_and_snapshot(adapter, tmp_path, reason, expected):
    repo = DecisionRepository(tmp_path / 'incomplete.db')
    decision = repo.create(DecisionCreate(**general_payload()), mode='live')
    def handler(request):
        body = envelope(adapter, {}).json()
        if adapter == 'deepseek': body.update(status='incomplete', incomplete_details={'reason': reason})
        else: body['choices'][0]['finish_reason'] = 'length' if reason == 'max_output_tokens' else reason
        return httpx2.Response(200, json=body)
    model = build_adapter(adapter, handler, repo)
    engine = WorkflowEngine(repo, model_provider=model, search_provider=DemoSearchProvider(), mode='live')
    try: result = engine.run(decision.id)
    finally: model.close()
    assert result.failure['code'] == 'model_incomplete'
    assert result.failure['incomplete_reason'] == expected
    calls = repo.list_provider_calls(decision.id)
    assert len(calls) == 2
    assert all(c['error_code'] == 'model_incomplete' and c['incomplete_reason'] == expected for c in calls)
    assert 'unit-secret' not in repr(calls) + result.model_dump_json()


def test_old_provider_ledger_migration_is_repeatable(tmp_path):
    from sqlalchemy import text
    path = tmp_path / 'old.db'
    repo = DecisionRepository(path)
    decision = repo.create(DecisionCreate(**general_payload()))
    call_id = repo.start_provider_attempt(context=ProviderCallContext(decision.id, 'clarifying'), provider='deepseek', attempt_number=1)
    repo.finish_provider_attempt(call_id, status='failed', error_code='model_invalid_response')
    with repo._engine.begin() as connection:
        connection.execute(text('ALTER TABLE provider_calls DROP COLUMN incomplete_reason'))
    repo._engine.dispose()
    for _ in range(2):
        migrated = DecisionRepository(path)
        assert migrated.list_provider_calls(decision.id)[0]['incomplete_reason'] is None
        assert migrated.list_provider_calls(decision.id)[0]['error_code'] == 'model_invalid_response'
        migrated._engine.dispose()


def test_schema_fallback_is_preserved_for_the_single_repair():
    seen = []
    valid = DemoModelProvider().generate('clarifying', context_with_evidence())
    def handler(request):
        seen.append(json.loads(request.content))
        if len(seen) == 1: return httpx2.Response(400, json={'error': {'message': 'json_schema unsupported'}})
        return compat_response({'summary': 'invalid'} if len(seen) == 2 else valid)
    model = compat_provider(handler)
    try: assert model.generate('clarifying', context_with_evidence()) == valid
    finally: model.close()
    assert len(seen) == 3
    assert seen[1]['response_format'] == seen[2]['response_format'] == {'type': 'json_object'}


def test_repair_transport_failure_has_no_additional_retries(adapter):
    seen, spy = [], AttemptSpy()
    def handler(request):
        seen.append(request)
        return envelope(adapter, {}) if len(seen) == 1 else httpx2.Response(503)
    model = build_adapter(adapter, handler, spy)
    try:
        with pytest.raises(ProviderError, match='model_upstream_unavailable'):
            model.generate('clarifying', context_with_evidence(), call_context=ProviderCallContext('id', 'clarifying'))
    finally: model.close()
    assert len(seen) == len(spy.finished) == 2


def test_output_budget_and_concise_prompt(adapter):
    from app.config import Settings
    from pydantic import ValidationError
    assert Settings().deepseek_max_output_tokens == 8192
    assert Settings(deepseek_max_output_tokens=16384).deepseek_max_output_tokens == 16384
    with pytest.raises(ValidationError): Settings(deepseek_max_output_tokens=16385)
    seen = []
    valid = DemoModelProvider().generate('clarifying', context_with_evidence())
    def handler(request):
        seen.append(json.loads(request.content))
        return envelope(adapter, valid)
    model = build_adapter(adapter, handler)
    try: model.generate('clarifying', context_with_evidence())
    finally: model.close()
    body = seen[0]
    assert body['max_output_tokens' if adapter == 'deepseek' else 'max_tokens'] == 8192
    instructions = body['instructions'] if adapter == 'deepseek' else body['messages'][0]['content']
    assert 'reasoning ≤ 200 字' in instructions and 'objection text ≤ 120 字' in instructions


@pytest.mark.parametrize('stage', ['challenging', 'delivering'])
@pytest.mark.parametrize('fails_twice', [False, True])
def test_live_smoke_reports_repair_attempts_and_terminal_subcodes(adapter, stage, fails_twice, monkeypatch):
    from app import main as main_module
    from tests.test_finals_delivery import load_script
    counts, lock = Counter(), Lock()
    def handler(request):
        current, context, _ = decode_stage_context(adapter, request)
        with lock:
            counts[current] += 1
            n = counts[current]
        output = DemoModelProvider().generate(current, context)
        if current == stage and (n == 1 or fails_twice):
            if current == 'challenging': output['objections'][0]['targets_assumption_ids'] = ['unit-secret']
            else: output['conditions'] = []
        return envelope(adapter, output)
    def factory(**kwargs):
        if adapter == 'deepseek':
            from app.providers.deepseek import DeepSeekModelProvider
            return DeepSeekModelProvider(**kwargs, transport=httpx2.MockTransport(handler), sleeper=lambda _: None)
        from app.providers.openai_compat import OpenAICompatModelProvider
        return OpenAICompatModelProvider(**kwargs, transport=httpx2.MockTransport(handler), sleeper=lambda _: None)
    monkeypatch.setattr(main_module, 'DeepSeekModelProvider' if adapter == 'deepseek' else 'OpenAICompatModelProvider', factory)
    result = load_script('live_smoke').run_smoke(authorized=True,
        settings=Settings(app_mode='live', enable_live_workflow=True,
            model_provider='deepseek' if adapter == 'deepseek' else 'openai_compat',
            deepseek_api_key='unit-secret', openai_compat_api_key='unit-secret', tavily_api_key='unit-secret'),
        search_provider=DemoSearchProvider())
    calls = result['provider_calls']
    assert all(set(call) == {'logical_operation', 'status', 'error_code', 'profile', 'model'} for call in calls)
    assert all(c['profile'] == ('deepseek' if adapter == 'deepseek' else 'openai_compat') and c['model'] for c in calls)
    relevant = [{key: c[key] for key in ('logical_operation', 'status', 'error_code')}
                for c in calls if c['logical_operation'].startswith(stage)]
    assert relevant == [
        {'logical_operation': stage, 'status': 'failed', 'error_code': 'model_contract_violation'},
        {'logical_operation': stage + ':repair', 'status': 'failed' if fails_twice else 'succeeded',
         'error_code': 'model_contract_violation' if fails_twice else None}]
    assert counts[stage] == 2
    assert result['passed'] is (not fails_twice)
    if fails_twice:
        assert result['failure']['stage'] == stage and result['failure']['code'] == 'model_contract_violation'
    else:
        assert result['final_status'] == 'deferred' and len(result['human_gates']) == 2
    assert 'unit-secret' not in json.dumps(result)

import json

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app
from app.providers.base import ProviderCallContext, ProviderError
from app.providers.demo import DemoModelProvider, DemoSearchProvider
from tests.test_deepseek_provider import AttemptSpy
from tests.test_stage_contracts import context_with_evidence
from tests.test_finals_scenarios import general_payload


def provider(handler, **kwargs):
    from app.providers.openai_compat import OpenAICompatModelProvider
    return OpenAICompatModelProvider(api_key=SecretStr('unit-secret'),
        base_url='https://dashscope.aliyuncs.com/compatible-mode/v1', model='fixture-model',
        transport=httpx2.MockTransport(handler), sleeper=lambda _: None, **kwargs)


def response(payload):
    return httpx2.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': json.dumps(payload)}}]})


def test_chat_schema_fallback_and_audit_are_bounded_and_redacted():
    context = context_with_evidence()
    expected = DemoModelProvider().generate('clarifying', context)
    requests, spy = [], AttemptSpy()
    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx2.Response(400, json={'error': {'param': 'response_format', 'message': 'json_schema is not supported; unit-secret'}})
        return response(expected)
    model = provider(handler, recorder=spy)
    try:
        assert model.generate('clarifying', context, call_context=ProviderCallContext('id', 'clarifying')) == expected
    finally:
        model.close()
    bodies = [json.loads(r.content) for r in requests]
    assert str(requests[0].url) == 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'
    assert bodies[0]['response_format']['type'] == 'json_schema'
    assert bodies[1]['response_format'] == {'type': 'json_object'}
    assert bodies[0]['model'] == 'fixture-model' and bodies[0]['stream'] is False
    assert bodies[0]['messages'][0]['role'] == 'system'
    assert len(spy.started) == 2 and len(spy.finished) == 2
    assert spy.finished[0][1] == 'failed' and spy.finished[1][1] == 'succeeded'
    assert 'unit-secret' not in repr(spy.__dict__)


@pytest.mark.parametrize('url', ['http://api.deepseek.com/v1', 'https://evil.example/v1',
    'https://api.deepseek.com.evil.example/v1', 'https://key@api.deepseek.com/v1',
    'https://api.deepseek.com:444/v1', 'https://dashscope.aliyuncs.com/v1?key=x',
    'https://api.deepseek.com/v1#fragment'])
def test_compat_rejects_unsafe_base_urls_before_transport(url):
    from app.providers.openai_compat import OpenAICompatModelProvider
    with pytest.raises(ValueError):
        OpenAICompatModelProvider(api_key=SecretStr('unit-secret'), base_url=url, model='fixture')


@pytest.mark.parametrize('status,calls', [(401, 1), (403, 1), (400, 1), (429, 3), (503, 3), (302, 1)])
def test_compat_errors_retry_only_bounded_safe_cases(status, calls):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx2.Response(status, json={'error': {'message': 'unit-secret'}}, headers={'location': 'https://evil.example/'})
    model = provider(handler)
    try:
        with pytest.raises(ProviderError) as exc:
            model.generate('clarifying', context_with_evidence())
        assert 'unit-secret' not in str(exc.value)
        assert len(seen) == calls
    finally: model.close()


def test_fallback_still_validates_model_output_and_member_schema():
    context = context_with_evidence() | {'_council_member': 'cfo'}
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        output = DemoModelProvider().generate('analyzing', context)
        output['role'] = 'risk'
        return response(output)
    model = provider(handler)
    try:
        with pytest.raises(ProviderError): model.generate('analyzing', context)
    finally: model.close()
    assert 'role' in seen[0]['response_format']['json_schema']['schema']['properties']
    assert 'cfo' in seen[0]['messages'][0]['content']


@pytest.mark.parametrize('key,enabled,search,unlocked', [('', True, 'search', False), ('model', False, 'search', False), ('model', True, '', False), ('model', True, 'search', True)])
def test_compat_live_gate_uses_selected_provider_key(tmp_path, key, enabled, search, unlocked):
    settings = Settings(app_mode='live', enable_live_workflow=enabled,
        model_provider='openai_compat', openai_compat_api_key=key, tavily_api_key=search,
        deepseek_api_key='irrelevant', openai_compat_model='fixture')
    with TestClient(create_app(tmp_path / 'db', settings=settings, model_provider=DemoModelProvider(), search_provider=DemoSearchProvider())) as client:
        assert client.get('/api/health').json()['live_available'] is unlocked
        assert client.post('/api/decisions', json=general_payload()).status_code == (201 if unlocked else 503)


@pytest.mark.parametrize('body,code', [(None, 'model_contract_violation'), ([], 'model_contract_violation'), ({}, 'model_contract_violation'), ({'choices': []}, 'model_contract_violation'),
    ({'choices': [{'finish_reason': 'length', 'message': {'content': '{}'}}]}, 'model_incomplete'),
    ({'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'not-json'}}]}, 'model_invalid_json'),
    ({'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': '[]'}}]}, 'model_contract_violation')])
def test_malformed_completion_has_one_repair_and_audit_closes(body, code):
    spy, requests = AttemptSpy(), []
    def handler(request):
        requests.append(request)
        return httpx2.Response(200, content=json.dumps(body))
    model = provider(handler, recorder=spy)
    try:
        with pytest.raises(ProviderError, match=code):
            model.generate('clarifying', context_with_evidence(), call_context=ProviderCallContext('id', 'clarifying'))
    finally: model.close()
    assert len(requests) == 2 and spy.finished == [(1, 'failed', code), (2, 'failed', code)]


@pytest.mark.parametrize('exception', [httpx2.ReadTimeout, httpx2.ConnectError])
def test_compat_transport_retries_and_redacts(exception):
    requests = []
    def handler(request):
        requests.append(request)
        raise exception('unit-secret', request=request)
    model = provider(handler)
    try:
        with pytest.raises(ProviderError) as error:
            model.generate('clarifying', context_with_evidence())
        assert 'unit-secret' not in str(error.value)
    finally: model.close()
    assert len(requests) == 3


def test_fallback_and_retries_share_a_three_attempt_budget():
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx2.Response(400, json={'error': {'message': 'json_schema unsupported'}})
        return httpx2.Response(503)
    model = provider(handler)
    try:
        with pytest.raises(ProviderError): model.generate('clarifying', context_with_evidence())
    finally: model.close()
    assert len(requests) == 3
    assert requests[1]['response_format']['type'] == requests[2]['response_format']['type'] == 'json_object'


def test_compat_mock_transport_runs_full_live_council_with_operation_ledger(tmp_path):
    from app.repository import DecisionRepository
    from app.workflow import WorkflowEngine
    from app.schemas import DecisionCreate
    repo = DecisionRepository(tmp_path / 'db')
    seen_roles = []
    def handler(request):
        body = json.loads(request.content)
        message = json.loads(body['messages'][1]['content'])
        stage, selected = message['stage'], message['context']
        selected.setdefault('evidence', [])
        selected['outputs'] = {
            'planning': selected.get('planning', {}),
            'researching': selected.get('research', {}),
            'challenging': selected.get('challenge', {}),
        }
        if stage == 'analyzing':
            system = body['messages'][0]['content']
            role = next(role for role in ('opportunity', 'cfo', 'risk', 'expert') if f'本次独立席位 {role}' in system)
            selected['_council_member'] = role
            seen_roles.append(role)
        return response(DemoModelProvider().generate(stage, selected))
    model = provider(handler, recorder=repo)
    engine = WorkflowEngine(repo, model_provider=model, search_provider=DemoSearchProvider(), mode='live')
    decision = repo.create(DecisionCreate(**general_payload()), mode='live')
    try:
        engine.run(decision.id); engine.confirm_clarification(decision.id)
        result = engine.run(decision.id)
    finally: model.close()
    assert result.status == 'awaiting_review', result.failure
    assert set(seen_roles) == {'opportunity', 'cfo', 'risk', 'expert'}
    calls = repo.list_provider_calls(decision.id)
    assert len(calls) == 8 and all(c['status'] == 'succeeded' for c in calls)
    assert {c['logical_operation'] for c in calls if c['stage'] == 'analyzing'} == {'analyzing:opportunity', 'analyzing:cfo', 'analyzing:risk', 'analyzing:expert'}
    assert not any(d.is_retrospective for d in repo.list())

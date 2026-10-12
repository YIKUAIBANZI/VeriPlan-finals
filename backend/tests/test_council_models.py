import json
from collections import Counter

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app
from app.providers.demo import DemoModelProvider, DemoSearchProvider
from app.providers.base import ProviderCallContext
from app.repository import DecisionRepository
from app.schemas import DecisionCreate
from tests.test_finals_scenarios import general_payload
from tests.test_live_hardening import decode_stage_context, envelope
from tests.test_finals_delivery import load_script


@pytest.mark.parametrize('value', ['cfo:bailian', 'unknown=deepseek', 'cfo=unknown', 'cfo=',
    'cfo=deepseek:', 'cfo=kimi:a:b', 'cfo=deepseek,cfo=kimi', 'cfo=deepseek,',
    'cfo=kimi:https://evil.test', 'cfo=deepseek=extra', 'cfo=kimi:bad model'])
def test_invalid_map_is_rejected(value):
    with pytest.raises(ValidationError):
        Settings(council_model_map=value)


def test_map_parsing_from_environment(monkeypatch):
    from app.providers.profiles import parse_council_model_map
    value = ' opportunity=bailian:qwen3.8-flash, cfo=deepseek,risk=minimax:MiniMax-M2.5-highspeed,expert=kimi '
    monkeypatch.setenv('COUNCIL_MODEL_MAP', value)
    assert parse_council_model_map(Settings().council_model_map) == {
        'opportunity': ('bailian', 'qwen3.8-flash'), 'cfo': ('deepseek', None),
        'risk': ('minimax', 'MiniMax-M2.5-highspeed'), 'expert': ('kimi', None)}
    assert parse_council_model_map('') == {}


@pytest.mark.parametrize('profile', ['deepseek', 'bailian', 'minimax', 'kimi'])
@pytest.mark.parametrize('key', [None, '', '  '])
def test_each_mapped_profile_key_is_required_even_with_injected_fakes(tmp_path, profile, key):
    settings = Settings(app_mode='live', enable_live_workflow=True, model_provider='openai_compat',
        openai_compat_api_key='private-default', tavily_api_key='private-search',
        council_model_map=f'expert={profile}', **{profile + '_api_key': key})
    with TestClient(create_app(tmp_path / 'db', settings=settings, model_provider=DemoModelProvider(), search_provider=DemoSearchProvider())) as client:
        health = client.get('/api/health').json()
        assert not health['live_available'] and not health['live_model_configured']
        response = client.post('/api/decisions', json=general_payload())
        assert response.status_code == 503 and profile in response.json()['detail']
        assert 'private-' not in response.text


def mock_factories(monkeypatch, handler):
    from app import main as main_module
    from app.providers.deepseek import DeepSeekModelProvider
    from app.providers.openai_compat import OpenAICompatModelProvider
    monkeypatch.setattr(main_module, 'DeepSeekModelProvider', lambda **kw: DeepSeekModelProvider(**kw, transport=httpx2.MockTransport(handler), sleeper=lambda _: None))
    monkeypatch.setattr(main_module, 'OpenAICompatModelProvider', lambda **kw: OpenAICompatModelProvider(**kw, transport=httpx2.MockTransport(handler), sleeper=lambda _: None))


def live_settings(**kwargs):
    return Settings(app_mode='live', enable_live_workflow=True, deepseek_api_key='private-default',
        tavily_api_key='private-search', bailian_api_key='private-bailian',
        minimax_api_key='private-minimax', kimi_api_key='private-kimi', **kwargs)


def test_profiles_use_distinct_requests_and_code_owned_labels_and_ledger(tmp_path, monkeypatch):
    seen = []
    def handler(request):
        body = json.loads(request.content)
        adapter = 'deepseek' if 'input' in body else 'compat'
        stage, context, _ = decode_stage_context(adapter, request)
        seen.append((request.url.host, body, context.get('_council_member')))
        return envelope(adapter, DemoModelProvider().generate(stage, context))
    mock_factories(monkeypatch, handler)
    settings = live_settings(council_model_map='opportunity=bailian:qwen3.8-flash,cfo=deepseek,risk=minimax:MiniMax-M2.5-highspeed,expert=kimi:kimi-k2.5')
    app = create_app(tmp_path / 'db', settings=settings, search_provider=DemoSearchProvider())
    with TestClient(app) as client:
        decision = client.post('/api/decisions', json=general_payload()).json()
        url = '/api/decisions/' + decision['id']
        client.post(url + '/run'); client.post(url + '/confirm'); client.post(url + '/run')
        snapshot = client.get(url).json()
        assert snapshot['status'] == 'awaiting_review', snapshot.get('failure')
        members = {m['role']: m for m in snapshot['outputs']['analyzing']['members']}
        assert members['opportunity']['model_label'] == '通义千问 qwen3.8-flash'
        assert members['cfo']['model_label'] == 'DeepSeek v4-flash'
        assert members['risk']['model_label'] == 'MiniMax M2.5-highspeed'
        assert members['expert']['model_label'] == 'Kimi kimi-k2.5'
        calls = app.state.repository.list_provider_calls(decision['id'])
        for role, profile in [('opportunity', 'bailian'), ('cfo', 'deepseek'), ('risk', 'minimax'), ('expert', 'kimi')]:
            call = next(c for c in calls if c['logical_operation'] == f'analyzing:{role}')
            assert call['profile'] == profile and call['model']
        assert 'private-' not in repr(calls) + json.dumps(snapshot)
    seats = {role: (host, body) for host, body, role in seen if role}
    assert seats['opportunity'][0] == 'dashscope.aliyuncs.com'
    assert seats['opportunity'][1]['enable_thinking'] is False
    assert seats['expert'][0] == 'api.moonshot.cn' and seats['expert'][1]['temperature'] == 1
    assert seats['risk'][0] == 'api.minimaxi.com' and 'temperature' not in seats['risk'][1]
    assert seats['cfo'][0] == 'api.deepseek.com' and 'reasoning' in seats['cfo'][1]


@pytest.mark.parametrize('fallback_failure', [None, 'contract', 'transport'])
def test_seat_fallback_is_one_physical_request_and_audited(monkeypatch, fallback_failure):
    counts = Counter()
    def handler(request):
        body = json.loads(request.content)
        adapter = 'deepseek' if 'input' in body else 'compat'
        stage, context, _ = decode_stage_context(adapter, request)
        role = context.get('_council_member')
        counts[adapter, role or stage] += 1
        if role == 'cfo' and adapter == 'compat':
            return envelope(adapter, {'summary': 'private-invalid'})
        if role == 'cfo' and fallback_failure == 'transport':
            return httpx2.Response(503)
        output = DemoModelProvider().generate(stage, context)
        if role == 'cfo' and fallback_failure == 'contract':
            output['evidence_ids'] = ['private-invalid']
        return envelope(adapter, output)
    mock_factories(monkeypatch, handler)
    result = load_script('live_smoke').run_smoke(authorized=True,
        settings=live_settings(council_model_map='cfo=bailian:qwen3.8-flash'), search_provider=DemoSearchProvider())
    assert result['passed'] is (fallback_failure is None)
    assert counts['compat', 'cfo'] == 2  # original + repair
    assert counts['deepseek', 'cfo'] == 1  # no nested retries/repair
    assert counts['deepseek', 'opportunity'] == counts['deepseek', 'risk'] == counts['deepseek', 'expert'] == 1
    calls = [c for c in result['provider_calls'] if c['logical_operation'].startswith('analyzing:cfo')]
    assert [c['logical_operation'] for c in calls] == ['analyzing:cfo', 'analyzing:cfo:repair', 'analyzing:cfo:fallback']
    assert [c['profile'] for c in calls] == ['bailian', 'bailian', 'deepseek']
    if fallback_failure is None:
        assert result['council']['cfo'] == {'profile': 'deepseek', 'model': 'deepseek-v4-flash', 'fallback_from': 'bailian'}
    else:
        assert result['council'] == {}  # No partial aggregate persists.
    assert 'private-' not in json.dumps(result)


def test_provider_metadata_migration_is_repeatable(tmp_path):
    from sqlalchemy import text
    path = tmp_path / 'old.db'
    repo = DecisionRepository(path)
    row = repo.create(DecisionCreate(**general_payload()))
    call = repo.start_provider_attempt(context=ProviderCallContext(row.id, 'planning'), provider='deepseek', attempt_number=1)
    repo.finish_provider_attempt(call, status='succeeded')
    with repo._engine.begin() as conn:
        conn.execute(text('ALTER TABLE provider_calls DROP COLUMN profile'))
        conn.execute(text('ALTER TABLE provider_calls DROP COLUMN model'))
    repo._engine.dispose()
    for _ in range(2):
        repo = DecisionRepository(path)
        saved = repo.list_provider_calls(row.id)[0]
        assert saved['profile'] is None and saved['model'] is None
        repo._engine.dispose()


@pytest.mark.parametrize('host', ['api.minimaxi.com', 'api.moonshot.cn'])
@pytest.mark.parametrize('template', ['http://{host}/v1', 'https://key@{host}/v1', 'https://{host}:444/v1',
    'https://{host}/v1?key=x', 'https://{host}/v1#x', 'https://{host}.evil.test/v1'])
def test_new_hosts_retain_all_url_safety_rules(host, template):
    from app.providers.openai_compat import validate_base_url
    with pytest.raises(ValueError):
        validate_base_url(template.format(host=host))


@pytest.mark.parametrize('profile', ['deepseek', 'bailian', 'minimax', 'kimi'])
def test_all_profiles_disable_proxy_inheritance_and_redirects(monkeypatch, profile):
    from pydantic import SecretStr
    from app.providers.deepseek import DeepSeekModelProvider
    from app.providers.openai_compat import OpenAICompatModelProvider
    from app.providers.profiles import PROFILE_URLS
    from app.providers.base import ProviderError
    from tests.test_stage_contracts import context_with_evidence
    # Inspect constructor options and still exercise a real client with MockTransport.
    real_client = httpx2.Client
    options, requests = [], []
    def client(**kwargs):
        options.append(kwargs)
        return real_client(**kwargs)
    monkeypatch.setattr(httpx2, 'Client', client)
    def redirect(request):
        requests.append(request)
        return httpx2.Response(302, headers={'location': 'https://evil.test/secret'})
    kwargs = dict(api_key=SecretStr('fake'), transport=httpx2.MockTransport(redirect))
    model = (DeepSeekModelProvider(**kwargs) if profile == 'deepseek' else
             OpenAICompatModelProvider(**kwargs, profile=profile, model='fixture', base_url=PROFILE_URLS[profile]))
    try:
        with pytest.raises(ProviderError): model.generate('planning', context_with_evidence())
    finally: model.close()
    assert options[0]['trust_env'] is False and options[0]['follow_redirects'] is False
    assert len(requests) == 1


def test_live_ablation_reuses_map_while_single_arms_use_default(tmp_path, monkeypatch):
    seen = []
    def handler(request):
        body = json.loads(request.content)
        adapter = 'deepseek' if 'input' in body else 'compat'
        stage, context, _ = decode_stage_context(adapter, request)
        seen.append((adapter, stage, context.get('_council_member')))
        return envelope(adapter, DemoModelProvider().generate(stage, context))
    mock_factories(monkeypatch, handler)
    result = load_script('ablation').run_ablation([{'question_id': 'Q1'} | general_payload()],
        output_dir=tmp_path / 'out', mode='live', authorized=True,
        settings=live_settings(council_model_map='expert=kimi:kimi-k2.5'), search_provider=DemoSearchProvider())
    assert result['failed'] == []
    assert seen.count(('compat', 'analyzing', 'expert')) == 1
    assert seen.count(('deepseek', 'ablation', None)) == 3
    assert len(seen) == 11


def test_demo_ignores_live_map_and_creates_no_real_adapters(tmp_path, monkeypatch):
    def forbidden(**kwargs):
        pytest.fail('Demo must not construct a real provider')
    from app import main as main_module
    monkeypatch.setattr(main_module, 'OpenAICompatModelProvider', forbidden)
    monkeypatch.setattr(main_module, 'DeepSeekModelProvider', forbidden)
    with TestClient(create_app(tmp_path / 'db', settings=Settings(app_mode='demo',
        council_model_map='expert=kimi', kimi_api_key='unused'))) as client:
        row = client.post('/api/decisions', json=general_payload()).json()
        url = '/api/decisions/' + row['id']
        client.post(url + '/run'); client.post(url + '/confirm'); client.post(url + '/run')
        snapshot = client.get(url).json()
        assert snapshot['status'] == 'awaiting_review'
        assert all(m['model_label'] == 'Demo · 合成模型' for m in snapshot['outputs']['analyzing']['members'])


@pytest.mark.parametrize('field', ['model_label', 'fallback_from'])
def test_model_cannot_forge_code_owned_member_metadata(field):
    from app.providers.contracts import validate_stage_output, stage_schema
    from tests.test_stage_contracts import context_with_evidence
    context = context_with_evidence() | {'_council_member': 'cfo'}
    payload = DemoModelProvider().generate('analyzing', context)
    payload[field] = 'forged'
    with pytest.raises(ValueError):
        validate_stage_output('analyzing', payload, context)
    assert field not in stage_schema('analyzing', member='cfo')[1]['properties']


def test_audit_failure_never_falls_back(tmp_path):
    from app.providers.base import ProviderError
    from app.workflow import WorkflowEngine
    class BrokenAudit(DemoModelProvider):
        def generate(self, *args, **kwargs):
            raise ProviderError('provider_audit_failed')
    repo = DecisionRepository(tmp_path / 'db')
    row = repo.create(DecisionCreate(**general_payload()))
    engine = WorkflowEngine(repo, council_providers={'cfo': BrokenAudit()})
    engine.run(row.id); engine.confirm_clarification(row.id)
    result = engine.run(row.id)
    assert result.failure['code'] == 'provider_audit_failed' and 'analyzing' not in result.outputs


@pytest.mark.parametrize('profile,model_name,extra', [
    ('bailian', 'qwen3.8-flash', {'enable_thinking': False}),
    ('kimi', 'kimi-k2.5', {'temperature': 1}),
])
def test_profile_parameters_survive_schema_downgrade_and_repair(profile, model_name, extra):
    from pydantic import SecretStr
    from app.providers.openai_compat import OpenAICompatModelProvider
    from app.providers.profiles import PROFILE_URLS
    from tests.test_openai_compat import response
    from tests.test_stage_contracts import context_with_evidence
    context = context_with_evidence()
    expected = DemoModelProvider().generate('planning', context)
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        if len(seen) == 1:
            return httpx2.Response(400, json={'error': {'message': 'json_schema unsupported'}})
        return response({} if len(seen) == 2 else expected)
    provider = OpenAICompatModelProvider(api_key=SecretStr('fake'), profile=profile,
        base_url=PROFILE_URLS[profile], model=model_name, transport=httpx2.MockTransport(handler))
    try:
        assert provider.generate('planning', context) == expected
    finally: provider.close()
    assert len(seen) == 3
    assert all(all(body[key] == value for key, value in extra.items()) for body in seen)
    assert seen[1]['response_format'] == seen[2]['response_format'] == {'type': 'json_object'}


def test_live_model_selected_expert_survives_planning_and_four_seat_validation(tmp_path, monkeypatch):
    expert_seen = []
    def handler(request):
        body = json.loads(request.content)
        adapter = 'deepseek' if 'input' in body else 'compat'
        stage, context, _ = decode_stage_context(adapter, request)
        output = DemoModelProvider().generate(stage, context)
        if stage == 'planning':
            output.update(expert_kind='legal_compliance', expert_reason='合同责任需要专项核对')
        if context.get('_council_member') == 'expert':
            expert_seen.append(output['expert_kind'])
        return envelope(adapter, output)
    mock_factories(monkeypatch, handler)
    app = create_app(tmp_path / 'db', settings=live_settings(council_model_map='expert=kimi'), search_provider=DemoSearchProvider())
    with TestClient(app) as client:
        row = client.post('/api/decisions', json=general_payload()).json()
        url = '/api/decisions/' + row['id']
        client.post(url + '/run'); client.post(url + '/confirm'); client.post(url + '/run')
        result = client.get(url).json()
        assert result['status'] == 'awaiting_review'
        assert result['outputs']['planning']['expert_source'] == 'model'
        assert expert_seen == ['legal_compliance']


def test_paratera_profile_is_allowlisted_and_labelled():
    from app.providers.profiles import PROFILE_URLS, model_label, parse_council_model_map

    assert PROFILE_URLS['paratera'] == 'https://llmapi.paratera.com/v1'
    assert parse_council_model_map('expert=paratera:GLM-5.3-Flash') == {'expert': ('paratera', 'GLM-5.3-Flash')}
    assert model_label('paratera', 'GLM-5.3-Flash') == '并行智算云 GLM-5.3-Flash'

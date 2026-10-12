import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.providers.demo import DemoModelProvider, DemoSearchProvider
from tests.test_finals_scenarios import general_payload

ROOT = Path(__file__).resolve().parents[2]


def test_export_contains_council_challenge_calibration_labels_and_outcomes(tmp_path):
    with TestClient(create_app(tmp_path / 'db')) as client:
        decision = client.post('/api/decisions', json=general_payload()).json()
        url = '/api/decisions/' + decision['id']
        client.post(url + '/run'); client.post(url + '/confirm'); client.post(url + '/run')
        client.post(url + '/objection-labels', json={'labels': {'O1': 'adopted'}})
        client.post(url + '/review', json={'action': 'accepted'})
        client.post(url + '/outcomes', json={'checkpoint': 'day_30', 'actuals': [{'assumption_id': 'A1', 'actual_value': 12000}]})
        markdown = client.get(url + '/export.md').text
        for expected in ('委员会分歧', 'opportunity', 'cfo', 'risk', 'expert', '个人长期发展专家', '按场景默认', '事前验尸', '新增风险数', 'O1', '采纳', '偏差警告', '不是预测', '回填对照', '12000', '-40'):
            assert expected in markdown
        assert '月售后工单量' not in markdown
        assert 'small_test_first' not in markdown  # translated recommendation


def test_live_smoke_refuses_without_explicit_authorization_and_writes_no_file(tmp_path):
    output = tmp_path / 'live.json'
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/live_smoke.py'), '--output', str(output)], capture_output=True, text=True)
    assert result.returncode != 0
    assert '--i-authorize-live' in result.stderr
    assert not output.exists()


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ablation_uses_same_fake_provider_and_emits_blind_risk_rows(tmp_path):
    calls = []
    class Fake(DemoModelProvider):
        def generate(self, stage, context, *, call_context=None):
            calls.append(stage)
            return super().generate(stage, context, call_context=call_context)
    ablation = load_script('ablation')
    summary = ablation.run_ablation([{'question_id': 'Q1'} | general_payload()],
        output_dir=tmp_path, model_provider=Fake(), search_provider=DemoSearchProvider())
    rows = list(csv.DictReader((tmp_path / 'risks.csv').open()))
    assert rows and set(rows[0]) == {'question_id', 'arm', 'risk_text', 'label'}
    assert {r['arm'] for r in rows} == {'A', 'B', 'C', 'D'}
    assert all(r['label'] == '' and r['question_id'] == 'Q1' for r in rows)
    assert calls.count('ablation') == 3 and calls.count('analyzing') == 4
    assert len(calls) == 11
    assert summary['risk_counts']['A'] >= 1 and summary['risk_counts']['B'] >= 1
    assert '人工标注' in (tmp_path / 'summary.md').read_text()


def test_ablation_cli_runs_offline(tmp_path):
    questions = tmp_path / 'questions.jsonl'
    questions.write_text(json.dumps({'question_id': 'Q1'} | general_payload()) + '\n')
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/ablation.py'), '--input', str(questions), '--output-dir', str(tmp_path / 'output')], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['mode'] == 'demo'


def test_live_smoke_full_path_uses_mock_transport_and_reports_only_safe_metrics(tmp_path, monkeypatch):
    import httpx2
    from app import main as main_module
    from app.config import Settings
    from app.providers.openai_compat import OpenAICompatModelProvider
    from app.providers.tavily import TavilySearchProvider
    from tests.test_openai_compat import response
    from tests.test_tavily_provider import tavily_response, tavily_result

    def model_handler(request):
        body = json.loads(request.content)
        message = json.loads(body['messages'][1]['content'])
        stage, context = message['stage'], message['context']
        context.setdefault('evidence', [])
        context['outputs'] = {'planning': context.get('planning', {}), 'researching': context.get('research', {}), 'challenging': context.get('challenge', {})}
        if stage == 'analyzing':
            context['_council_member'] = next(role for role in ('opportunity', 'cfo', 'risk', 'expert') if f'本次独立席位 {role}' in body['messages'][0]['content'])
        return response(DemoModelProvider().generate(stage, context))
    def search_handler(request):
        body = json.loads(request.content)
        slug = 'risk' if 'risk' in body['query'] else 'baseline'
        return httpx2.Response(200, json=tavily_response([tavily_result(title=slug, content=f'Evidence for {slug}', url=f'https://example.com/{slug}')]))
    monkeypatch.setattr(main_module, 'OpenAICompatModelProvider', lambda **kwargs: OpenAICompatModelProvider(**kwargs, transport=httpx2.MockTransport(model_handler), sleeper=lambda _: None))
    monkeypatch.setattr(main_module, 'TavilySearchProvider', lambda **kwargs: TavilySearchProvider(**kwargs, transport=httpx2.MockTransport(search_handler), sleeper=lambda _: None))
    smoke = load_script('live_smoke')
    result = smoke.run_smoke(authorized=True, settings=Settings(app_mode='live', enable_live_workflow=True,
        model_provider='openai_compat', openai_compat_api_key='never-print-model', tavily_api_key='never-print-search'))
    assert result['passed'] and result['within_120_seconds']
    assert result['final_status'] == 'deferred'
    assert result['provider_call_count'] == 10  # eight model calls and two search queries
    assert len(result['provider_calls']) == 10
    assert all(set(call) == {'logical_operation', 'status', 'error_code', 'profile', 'model'} for call in result['provider_calls'])
    assert all(call['status'] == 'succeeded' and call['error_code'] is None for call in result['provider_calls'])
    assert len(result['human_gates']) == 2
    assert all(stage in result['stages'] for stage in ('clarifying', 'planning', 'researching', 'analyzing', 'challenging', 'delivering'))
    assert 'never-print' not in json.dumps(result)


def test_ablation_cli_live_requires_its_own_authorization(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/ablation.py'), '--input', str(tmp_path / 'missing.jsonl'), '--output-dir', str(tmp_path / 'out'), '--live'], capture_output=True, text=True)
    assert result.returncode != 0 and '--i-authorize-live' in result.stderr
    assert not (tmp_path / 'out').exists()


def test_live_smoke_python_entry_also_requires_authorization():
    import pytest
    with pytest.raises(ValueError, match='i-authorize-live'):
        load_script('live_smoke').run_smoke(authorized=False)

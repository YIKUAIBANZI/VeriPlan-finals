import pytest
from fastapi.testclient import TestClient
from tests.helpers import login

from app.main import create_app
from app.config import Settings
from app.schemas import DecisionStatus
from app.state_machine import transition, InvalidTransition
from tests.test_finals_scenarios import general_payload


def retrospective_payload(actual=60, category='revenue', predicted=100, confidence=80):
    return dict(question='过去是否应该投入预算扩大工作室业务？', scenario='general',
                decision_date='2026-09-01', assumptions=[dict(label='预测值', category=category,
                value=predicted, unit='元', confidence=confidence)],
                actuals=[dict(assumption_id='A1', actual_value=actual)], note='人工回溯样本')


def test_retrospective_is_terminal_and_profile_computes_numbers(tmp_path):
    with TestClient(create_app(tmp_path / 'db')) as client:
        login(client)
        for actual in (60, 80):
            response = client.post('/api/retrospectives', json=retrospective_payload(actual))
            assert response.status_code == 201
            sample = response.json()
            assert sample['status'] == 'retrospective' and sample['is_retrospective']
            assert sample['outcomes'][0]['actuals'][0]['error_pct'] == actual - 100
            for action in ('run', 'retry', 'confirm'):
                assert client.post(f"/api/decisions/{sample['id']}/{action}").status_code == 409
        profile = client.get('/api/calibration').json()
        category = next(c for c in profile['categories'] if c['category'] == 'revenue')
        assert category == dict(category='revenue', n=2, mean_bias_pct=-30.0,
                                hit_rate=0.5, mean_confidence=80.0, overconfidence_gap=30.0)
        assert {s['source'] for s in profile['samples']} == {'retrospective'}
        assert {s['mode'] for s in profile['samples']} == {'demo'}
        assert all(s['decision_id'] for s in profile['samples'])
    for status in DecisionStatus:
        with pytest.raises(InvalidTransition): transition(DecisionStatus.retrospective, status)


def test_profile_skips_zero_and_isolates_modes(tmp_path):
    path = tmp_path / 'db'
    with TestClient(create_app(path)) as client:
        login(client)
        response = client.post('/api/retrospectives', json=retrospective_payload(predicted=0))
        assert response.status_code == 201
        actual = response.json()['outcomes'][0]['actuals'][0]
        assert actual['error_pct'] is None and actual['calculation_note'] == '不可计算：预测值为 0'
        profile = client.get('/api/calibration').json()
        assert profile['categories'] == []
        assert len(profile['samples']) == 1
    with TestClient(create_app(path, settings=Settings(app_mode='live'))) as client:
        login(client)
        assert client.get('/api/calibration').json()['samples'] == []
        assert client.post('/api/retrospectives', json=retrospective_payload()).status_code == 503


def test_outcomes_gate_overwrite_validation_and_warning_injection(tmp_path):
    with TestClient(create_app(tmp_path / 'db')) as client:
        login(client)
        for _ in range(2):
            assert client.post('/api/retrospectives', json=retrospective_payload()).status_code == 201
        decision = client.post('/api/decisions', json=general_payload()).json()
        url = '/api/decisions/' + decision['id']
        data = dict(checkpoint='day_30', actuals=[dict(assumption_id='A1', actual_value=12000)], note='已回填')
        assert client.post(url + '/outcomes', json=data).status_code == 409
        client.post(url + '/run'); client.post(url + '/confirm'); client.post(url + '/run')
        result = client.get(url).json()
        warnings = result['outputs']['challenging']['calibration_warnings']
        assert warnings[0]['bias_pct'] == -40
        assert warnings[0]['adjusted_reference'] == {'A1': 12000}
        assert '高估' in warnings[0]['message'] and '不是预测' in warnings[0]['message']
        client.post(url + '/review', json={'action': 'accepted'})
        saved = client.post(url + '/outcomes', json=data)
        assert saved.status_code == 200
        assert saved.json()['outcomes'][0]['actuals'][0]['error_pct'] == -40
        data['actuals'][0]['actual_value'] = 16000
        assert len(client.post(url + '/outcomes', json=data).json()['outcomes']) == 1
        for invalid in [dict(assumption_id='A9', actual_value=10), dict(assumption_id='A1', actual_value=10, error_pct=0)]:
            assert client.post(url + '/outcomes', json=data | {'actuals': [invalid]}).status_code == 422
        assert client.post(url + '/outcomes', json=data | {'actuals': data['actuals'] * 2}).status_code == 422
        assert client.post(url + '/outcomes', json=data | {'checkpoint': 'day_7'}).status_code == 422
        profile = client.get('/api/calibration').json()
        assert next(c for c in profile['categories'] if c['category'] == 'revenue')['n'] == 3
        assert {s['source'] for s in profile['samples']} == {'demo', 'retrospective'}


@pytest.mark.parametrize('category,actual,word', [('cost', 140, '低估了成本'), ('time', 140, '低估了耗时'), ('revenue', 140, '低估'), ('volume', 60, '高估')])
def test_warning_directions_and_thresholds(tmp_path, category, actual, word):
    from app.calibration import calibration_profile, calibration_warnings
    from app.repository import DecisionRepository
    from app.schemas import RetrospectiveCreate, DecisionCreate
    repo = DecisionRepository(tmp_path / 'db')
    current = general_payload()
    current['assumptions'][0]['category'] = category
    for i in range(2):
        repo.create_retrospective(RetrospectiveCreate(**retrospective_payload(actual, category)), mode='demo')
        profile = calibration_profile(repo.list(), mode='demo')
        decision = repo.create(DecisionCreate(**current))
        warnings = calibration_warnings(profile, decision.assumptions)
        assert bool(warnings) == (i == 1)
    assert word in warnings[0]['message']


def test_retrospective_invalid_actual_does_not_create_partial_record(tmp_path):
    with TestClient(create_app(tmp_path / 'db')) as client:
        login(client)
        data = retrospective_payload()
        data['actuals'][0]['assumption_id'] = 'A2'
        assert client.post('/api/retrospectives', json=data).status_code == 422
        assert client.get('/api/decisions').json() == []


def test_signed_error_and_hit_boundary_are_computed_without_rounding_bias():
    from app.calibration import error_pct
    assert error_pct(-100, -140) == -40
    assert error_pct(100, 120) == 20
    assert error_pct(100, 120.001) > 20
    assert error_pct(0, 10) is None


def test_cross_mode_outcomes_and_labels_are_read_only(tmp_path):
    path = tmp_path / 'db'
    with TestClient(create_app(path)) as client:
        login(client)
        decision = client.post('/api/decisions', json=general_payload()).json()
        url = '/api/decisions/' + decision['id']
        client.post(url + '/run'); client.post(url + '/confirm'); client.post(url + '/run')
        client.post(url + '/review', json={'action': 'deferred'})
    from app.providers.demo import DemoModelProvider, DemoSearchProvider
    settings = Settings(app_mode='live', enable_live_workflow=True,
                        deepseek_api_key='fixture', tavily_api_key='fixture')
    with TestClient(create_app(path, settings=settings, model_provider=DemoModelProvider(), search_provider=DemoSearchProvider())) as client:
        login(client)
        before = client.get(url).json()
        assert client.post(url + '/objection-labels', json={'labels': {'O1': 'adopted'}}).status_code == 409
        assert client.post(url + '/outcomes', json={'checkpoint': 'custom', 'actuals': [{'assumption_id': 'A1', 'actual_value': 1}]}).status_code == 409
        assert client.get(url).json() == before


def test_extreme_but_finite_samples_do_not_overflow_category_mean(tmp_path):
    with TestClient(create_app(tmp_path / 'db')) as client:
        login(client)
        for _ in range(2):
            assert client.post('/api/retrospectives', json=retrospective_payload(actual=1e306, predicted=1)).status_code == 201
        profile = client.get('/api/calibration').json()
        assert profile['categories'][0]['n'] == 2
        assert profile['categories'][0]['mean_bias_pct'] == pytest.approx(1e308)

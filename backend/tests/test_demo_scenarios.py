import pytest
from fastapi.testclient import TestClient
from tests.helpers import login

from app.main import create_app
from tests.test_finals_scenarios import general_payload


@pytest.mark.parametrize('scenario', ['ai_tool_pilot', 'first_hire', 'big_order', 'marketing_spend', 'general'])
def test_all_scenarios_have_disagreement_blocker_novel_risk_and_synthetic_calibration(tmp_path, scenario):
    path = tmp_path / 'db'
    with TestClient(create_app(path)) as client:
        login(client)
        created = client.post('/api/decisions', json=general_payload(scenario=scenario, horizon_days=30)).json()
        url = '/api/decisions/' + created['id']
        client.post(url + '/run'); client.post(url + '/confirm'); client.post(url + '/run')
        result = client.get(url).json()
        assert result['status'] == 'awaiting_review', result['failure']
        assert result['outputs']['analyzing']['disagreement']['is_split']
        challenge = result['outputs']['challenging']
        assert any(o['severity'] == 'blocker' for o in challenge['objections'])
        assert challenge['novel_objection_count'] >= 1
        assert challenge['calibration_warnings']
        assert result['memo']['time_window'] == '30 天'
        assert result['memo']['action_plan'][-1]['days'].endswith('30')
        if scenario != 'ai_tool_pilot':
            assert '工单' not in str(result['outputs'])
        seeds = [d for d in client.get('/api/decisions').json() if d['is_retrospective']]
        assert len(seeds) == 2
        assert all(d['mode'] == 'demo' and '合成' in d['question'] for d in seeds)
        samples = client.get('/api/calibration').json()['samples']
        assert all(s['is_synthetic'] for s in samples)
    with TestClient(create_app(path)) as client:
        login(client)
        assert len([d for d in client.get('/api/decisions').json() if d['is_retrospective']]) == 2

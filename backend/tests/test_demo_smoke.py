from fastapi.testclient import TestClient
from tests.helpers import login
from app.main import create_app
from tests.test_api import payload


def test_demo_fixture_delivers_skeptic_and_14_day_actions(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_MODE', 'demo')
    with TestClient(create_app(tmp_path / 'db')) as client:
        login(client)
        decision = client.post('/api/decisions', json=payload()).json()
        url = '/api/decisions/' + decision['id']
        assert client.post(url + '/run').status_code == 202
        assert client.get(url).json()['status'] == 'awaiting_confirmation'
        client.post(url + '/confirm')
        client.post(url + '/run')
        result = client.get(url).json()
        assert result['status'] == 'awaiting_review'
        assert len(result['evidence']) >= 3
        assert result['outputs']['challenging']['hidden_assumptions']
        assert len(result['memo']['action_plan']) >= 3
        assert [item['days'] for item in result['memo']['action_plan']] == [
            '1–3',
            '4–10',
            '11–14',
        ]
        assert sum(item['budget_limit'] for item in result['memo']['action_plan']) <= result['budget_limit']
        assert all({'owner','metric','stop_condition'} <= item.keys() for item in result['memo']['action_plan'])
        assert client.post(url + '/review', json={'action':'deferred','note':'Need real evidence'}).json()['review_note'] == 'Need real evidence'

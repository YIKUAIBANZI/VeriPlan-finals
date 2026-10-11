from fastapi.testclient import TestClient

from app.main import create_app
from app.repository import DecisionRepository
from app.workflow import WorkflowEngine
from tests.test_repository import sample_decision


def payload() -> dict:
    return {"question": "Should we pilot AI support before a full rollout?", "time_window": "14 days", "budget_limit": 8000, "primary_goal": "Reduce repetitive support workload safely"}


def test_api_requires_confirmation_before_demo_workflow_can_finish(tmp_path):
    client = TestClient(create_app(tmp_path / "veriplan.db"))
    assert client.get('/api/health').json()['mode'] == 'demo'
    created = client.post("/api/decisions", json=payload()).json()
    url = f"/api/decisions/{created['id']}"
    assert client.post(url + '/review', json={'action':'accepted'}).status_code == 409
    response = client.post(url + '/run')
    assert response.status_code == 202
    assert response.json()['status'] == 'clarifying'
    assert client.get(url).json()['status'] == 'awaiting_confirmation'
    assert client.post(url + '/run').status_code == 409
    assert client.post(url + '/confirm').json()['status'] == 'planning'
    assert client.post(url + '/run').status_code == 202
    assert client.get(url).json()['status'] == 'awaiting_review'
    assert client.post(url + '/review', json={'action':'accepted'}).json()['status'] == 'accepted'
    assert client.get('/api/decisions').json()[0]['id'] == created['id']


def test_create_normalizes_supported_window_and_rejects_other_windows(tmp_path):
    client = TestClient(create_app(tmp_path / "window.db"))
    supported = payload()
    supported["time_window"] = "14 days"
    created = client.post("/api/decisions", json=supported)

    assert created.status_code == 201
    assert created.json()["time_window"] == "14 天"
    decision_id = created.json()["id"]
    assert client.get(f"/api/decisions/{decision_id}").json()["time_window"] == "14 天"

    for unsupported in ("3 days", "30 天"):
        rejected = dict(supported, time_window=unsupported)
        assert client.post("/api/decisions", json=rejected).status_code == 422

    assert len(client.get("/api/decisions").json()) == 1


def test_missing_decisions_and_untrusted_create_fields(tmp_path):
    client = TestClient(create_app(tmp_path / 'db'))
    assert client.get('/api/decisions/missing').status_code == 404
    for operation in ['run','retry','confirm','review']:
        assert client.post('/api/decisions/missing/' + operation, json={'action':'accepted'}).status_code == 404
    for key in ['status','prompt','file_path','api_key']:
        assert client.post('/api/decisions', json=payload() | {key:'x'}).status_code == 422


def test_live_mode_is_unavailable_and_secrets_are_never_returned(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_MODE', 'live')
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'private-test-secret')
    client = TestClient(create_app(tmp_path / 'db'))
    health = client.get('/api/health')
    assert health.json()['mode'] == 'live'
    assert health.json()['live_available'] is False
    assert 'private-test-secret' not in health.text
    assert client.post('/api/decisions', json=payload()).status_code == 503


def test_markdown_export_requires_a_delivered_memo_and_sets_download_headers(tmp_path):
    client = TestClient(create_app(tmp_path / "export.db"))
    assert client.get("/api/decisions/missing/export.md").status_code == 404

    created = client.post("/api/decisions", json=payload()).json()
    export_url = f"/api/decisions/{created['id']}/export.md"
    assert client.get(export_url).status_code == 409

    client.post(f"/api/decisions/{created['id']}/run")
    client.post(f"/api/decisions/{created['id']}/confirm")
    client.post(f"/api/decisions/{created['id']}/run")
    response = client.get(export_url)

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/markdown; charset=utf-8"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="veriplan-{created["id"]}.md"'
    )
    assert "# VeriPlan 决策 Memo" in response.text
    assert "Demo 模式" in response.text


def test_markdown_export_is_read_only_across_application_modes(tmp_path):
    path = tmp_path / "cross-mode.db"
    repository = DecisionRepository(path)
    engine = WorkflowEngine(repository, mode="live")
    decision = repository.create(sample_decision(), mode="live")
    engine.run(decision.id)
    engine.confirm_clarification(decision.id)
    engine.run(decision.id)
    repository._engine.dispose()

    demo_client = TestClient(create_app(path))
    response = demo_client.get(f"/api/decisions/{decision.id}/export.md")

    assert response.status_code == 200
    assert "Live 模式" in response.text

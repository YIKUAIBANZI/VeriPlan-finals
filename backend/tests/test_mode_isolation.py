import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.providers.base import ProviderCallContext
from app.providers.demo import DemoModelProvider, DemoSearchProvider
from app.repository import DecisionRepository
from app.schemas import DecisionStatus
from app.workflow import WorkflowEngine
from tests.test_repository import sample_decision


class CountingModel:
    def __init__(self):
        self.calls: list[str] = []

    def generate(self, stage, context, *, call_context=None):
        self.calls.append(stage)
        raise AssertionError("cross-mode workflow called the model")


class CountingSearch:
    def __init__(self):
        self.calls: list[str] = []

    def search(self, query, *, call_context=None):
        self.calls.append(query)
        raise AssertionError("cross-mode workflow called search")


class FailingModel:
    def generate(self, stage, context, *, call_context=None):
        raise RuntimeError("fixture failure")


def _engine(repository, mode, *, model=None, search=None):
    return WorkflowEngine(
        repository,
        model_provider=model,
        search_provider=search,
        mode=mode,
    )


@pytest.mark.parametrize(
    ("decision_mode", "engine_mode"),
    [("live", "demo"), ("demo", "live")],
)
def test_cross_mode_run_is_rejected_before_state_or_provider_change(
    tmp_path, decision_mode, engine_mode
):
    repository = DecisionRepository(tmp_path / "mode.db")
    decision = repository.create(sample_decision(), mode=decision_mode)
    model = CountingModel()
    search = CountingSearch()
    engine = _engine(repository, engine_mode, model=model, search=search)
    before = repository.get(decision.id).model_dump(mode="json")

    with pytest.raises(ValueError, match="mode"):
        engine.run(decision.id)

    assert repository.get(decision.id).model_dump(mode="json") == before
    assert model.calls == []
    assert search.calls == []


@pytest.mark.parametrize("operation", ["confirm", "retry", "review"])
@pytest.mark.parametrize(
    ("decision_mode", "engine_mode"),
    [("live", "demo"), ("demo", "live")],
)
def test_cross_mode_mutations_leave_valid_historical_task_unchanged(
    tmp_path, operation, decision_mode, engine_mode
):
    repository = DecisionRepository(tmp_path / f"{operation}.db")
    owner = _engine(repository, decision_mode)
    decision = repository.create(sample_decision(), mode=decision_mode)

    if operation == "confirm":
        owner.run(decision.id)
    elif operation == "retry":
        failing = _engine(repository, decision_mode, model=FailingModel())
        failing.run(decision.id)
        assert repository.get(decision.id).status is DecisionStatus.failed
    else:
        owner.run(decision.id)
        owner.confirm_clarification(decision.id)
        owner.run(decision.id)
        assert repository.get(decision.id).status is DecisionStatus.awaiting_review

    historical = _engine(repository, engine_mode)
    before = repository.get(decision.id).model_dump(mode="json")
    with pytest.raises(ValueError, match="mode"):
        if operation == "confirm":
            historical.confirm_clarification(decision.id)
        elif operation == "retry":
            historical.retry(decision.id)
        else:
            historical.apply_review(
                decision.id,
                action="accepted",
                note="must remain unchanged",
            )

    assert repository.get(decision.id).model_dump(mode="json") == before


def test_run_prepared_rechecks_mode_before_resuming_a_queued_task(tmp_path):
    repository = DecisionRepository(tmp_path / "prepared.db")
    decision = repository.create(sample_decision(), mode="live")
    owner = _engine(repository, "live")
    owner.prepare_run(decision.id)
    historical = _engine(repository, "demo", model=CountingModel())
    before = repository.get(decision.id).model_dump(mode="json")

    with pytest.raises(ValueError, match="mode"):
        historical.run_prepared(decision.id)

    assert repository.get(decision.id).model_dump(mode="json") == before
    assert historical._model.calls == []


def test_recovery_only_marks_current_mode_queries_calls_and_workflows(tmp_path):
    repository = DecisionRepository(tmp_path / "recovery.db")
    demo = repository.create(sample_decision(), mode="demo")
    live = repository.create(sample_decision(), mode="live")
    for decision in (demo, live):
        query = repository.sync_research_queries(decision.id, ["baseline"])[0]
        repository.start_research_query(decision.id, query.id)
        repository.start_provider_attempt(
            context=ProviderCallContext(
                decision_id=decision.id,
                logical_operation="researching",
                stage="researching",
                research_query_id=query.id,
            ),
            provider="fixture",
            attempt_number=1,
        )

    queued_live = repository.create(sample_decision(), mode="live")
    _engine(repository, "live").prepare_run(queued_live.id)
    before_live = repository.get(queued_live.id).model_dump(mode="json")

    _engine(repository, "demo").recover_interrupted()

    assert repository.get(demo.id).research_queries[0].status.value == "failed"
    assert repository.get(live.id).research_queries[0].status.value == "running"
    assert repository.list_provider_calls(demo.id)[0]["status"] == "failed"
    assert repository.list_provider_calls(live.id)[0]["status"] == "running"
    assert repository.get(queued_live.id).model_dump(mode="json") == before_live


def test_http_review_rejects_a_decision_from_another_mode(tmp_path):
    database = tmp_path / "http.db"
    demo_app = create_app(database)
    with TestClient(demo_app) as demo_client:
        decision_id = demo_client.post(
            "/api/decisions", json=sample_decision().model_dump(mode="json")
        ).json()["id"]
        url = f"/api/decisions/{decision_id}"
        assert demo_client.post(url + "/run").status_code == 202
        assert demo_client.post(url + "/confirm").status_code == 200
        assert demo_client.post(url + "/run").status_code == 202
        assert demo_client.get(url).json()["status"] == "awaiting_review"

    live_settings = Settings(
        app_mode="live",
        enable_live_workflow=True,
        deepseek_api_key="fixture-model-key",
        tavily_api_key="fixture-search-key",
    )
    live_app = create_app(
        database,
        settings=live_settings,
        model_provider=DemoModelProvider(),
        search_provider=DemoSearchProvider(),
    )
    with TestClient(live_app) as live_client:
        response = live_client.post(
            f"/api/decisions/{decision_id}/review",
            json={"action": "accepted", "note": "must not persist"},
        )

    assert response.status_code == 409
    assert DecisionRepository(database).get(decision_id).status is DecisionStatus.awaiting_review

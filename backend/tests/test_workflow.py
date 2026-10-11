from app.repository import DecisionRepository
from app.providers.base import ProviderError
from app.schemas import BusinessBaseline, DecisionStatus
from app.workflow import WorkflowEngine

from tests.test_repository import sample_decision


def test_demo_workflow_requires_confirmation_then_runs_remaining_stages(tmp_path):
    repository = DecisionRepository(tmp_path / "veriplan.db")
    decision = repository.create(sample_decision())

    engine = WorkflowEngine(repository)
    clarification = engine.run(decision.id)

    assert clarification.status is DecisionStatus.awaiting_confirmation
    assert [event.stage for event in clarification.events if event.status == "completed"] == ["clarifying"]

    engine.confirm_clarification(decision.id)
    snapshot = engine.run(decision.id)

    assert snapshot.status is DecisionStatus.awaiting_review
    assert [event.stage for event in snapshot.events if event.status == "completed"] == [
        "clarifying", "planning", "researching", "analyzing", "challenging", "delivering"
    ]
    assert len(snapshot.evidence) >= 3
    assert snapshot.memo["recommendation"] == "pilot_before_rollout"
    assert snapshot.memo["support_score"] <= 79


def ready(repository, engine, *, mode="demo"):
    decision = repository.create(sample_decision(), mode=mode)
    engine.run(decision.id)
    engine.confirm_clarification(decision.id)
    return decision.id


def test_demo_outputs_reference_synthetic_evidence_and_constraints(tmp_path):
    repository = DecisionRepository(tmp_path / 'db')
    engine = WorkflowEngine(repository)
    snapshot = engine.run(ready(repository, engine))
    assert snapshot.mode == 'demo'
    assert all(card.is_demo and '.invalid/' in card.source_url for card in snapshot.evidence)
    assert len(set(snapshot.outputs['planning']['queries'])) >= 2
    assert len(snapshot.outputs['analyzing']['analyses']) == 3
    assert snapshot.outputs['challenging']['hidden_assumptions']
    assert snapshot.memo['facts'] and snapshot.memo['inferences']
    assert snapshot.memo['support_score'] <= 59  # synthetic fixtures cannot establish real support
    assert snapshot.memo['research_gaps']
    ids = {card.id for card in snapshot.evidence}
    assert all(set(f['evidence_ids']) <= ids for f in snapshot.memo['facts'])
    actions = snapshot.memo['action_plan']
    assert len(actions) >= 3
    assert all({'owner','metric','stop_condition','days','action','budget_limit'} <= action.keys() for action in actions)
    assert sum(action['budget_limit'] for action in actions) <= snapshot.budget_limit
    assert snapshot.primary_goal in str(actions)
    assert snapshot.time_window == snapshot.memo['time_window']
    assert "抽样最近 7 天售后工单" in str(snapshot.outputs)


def test_demo_workflow_labels_complete_baseline_estimate_as_user_input(tmp_path):
    repository = DecisionRepository(tmp_path / "db")
    engine = WorkflowEngine(repository)
    payload = sample_decision().model_copy(
        update={
            "business_baseline": BusinessBaseline(
                monthly_ticket_volume=1_000,
                repetitive_ticket_rate=60,
                average_handle_minutes=8,
                loaded_hourly_cost=40,
                expected_ai_resolution_rate=70,
                review_minutes_per_ai_ticket=1,
                monthly_tool_cost=800,
                max_acceptable_error_rate=2,
            )
        }
    )
    decision = repository.create(payload)
    engine.run(decision.id)
    engine.confirm_clarification(decision.id)

    snapshot = engine.run(decision.id)

    serialized_outputs = str(snapshot.outputs)
    assert "用户输入试算，不是已验证收益" in serialized_outputs
    assert "1160.0" in serialized_outputs
    assert "抽样最近 7 天售后工单" not in serialized_outputs


def test_stage_failure_is_redacted_and_retry_preserves_completed_work(tmp_path):
    repository = DecisionRepository(tmp_path / 'db')
    engine = WorkflowEngine(repository)
    decision_id = ready(repository, engine)
    original = engine._run_stage
    def failing(stage, snapshot):
        if stage == 'analyzing':
            raise RuntimeError('secret=must-never-return')
        return original(stage, snapshot)
    engine._run_stage = failing
    failed = engine.run(decision_id)
    assert failed.status is DecisionStatus.failed
    assert failed.failure['stage'] == 'analyzing'
    assert 'must-never-return' not in failed.model_dump_json()
    engine._run_stage = original
    result = engine.retry(decision_id)
    assert result.status is DecisionStatus.awaiting_review
    assert result.failure is None
    assert len(result.evidence) == 3
    assert sum(e.stage == 'planning' and e.status == 'completed' for e in result.events) == 1


def test_provider_failure_persists_only_safe_error_code(tmp_path):
    class RateLimitedProvider:
        def generate(self, stage, context, *, call_context=None):
            raise ProviderError('model_rate_limited')

    repository = DecisionRepository(tmp_path / 'db')
    engine = WorkflowEngine(repository, model_provider=RateLimitedProvider())
    decision = repository.create(sample_decision())

    failed = engine.run(decision.id)

    assert failed.status is DecisionStatus.failed
    assert failed.failure == {
        'stage': 'clarifying',
        'code': 'model_rate_limited',
        'message': '阶段执行失败，请重试；已完成输出已保留。',
    }
    assert 'Model provider failed' not in failed.model_dump_json()


def test_interrupted_stage_recovers_after_repository_restart(tmp_path):
    path = tmp_path / 'db'
    repository = DecisionRepository(path)
    engine = WorkflowEngine(repository)
    decision_id = ready(repository, engine)
    repository.save_stage_output(decision_id, 'planning', {'summary':'persisted', 'queries':['baseline','risk']})
    repository.update_status(decision_id, DecisionStatus.researching)
    restarted = WorkflowEngine(DecisionRepository(path))
    restarted.recover_interrupted()
    failed = repository.get(decision_id)
    assert failed.status is DecisionStatus.failed
    assert failed.failure['code'] == 'interrupted'
    assert restarted.retry(decision_id).status is DecisionStatus.awaiting_review


def test_reservation_prevents_duplicate_run_and_confirmation_bypass(tmp_path):
    import pytest
    repository = DecisionRepository(tmp_path / 'db')
    engine = WorkflowEngine(repository)
    decision = repository.create(sample_decision())
    with pytest.raises(ValueError):
        engine.confirm_clarification(decision.id)
    assert engine.prepare_run(decision.id).status is DecisionStatus.clarifying
    with pytest.raises(ValueError):
        engine.prepare_run(decision.id)
    engine.run_prepared(decision.id)
    assert repository.get(decision.id).status is DecisionStatus.awaiting_confirmation


def test_planning_keeps_only_first_three_unique_normalized_queries(tmp_path):
    from app.providers.demo import DemoModelProvider

    class FiveQueryModel(DemoModelProvider):
        def generate(self, stage, context, *, call_context=None):
            output = super().generate(stage, context, call_context=call_context)
            if stage == "planning":
                output["queries"] = [
                    "  baseline  ",
                    "risk",
                    "BASELINE",
                    "cost",
                    "market",
                ]
            return output

    repository = DecisionRepository(tmp_path / "db")
    engine = WorkflowEngine(repository, model_provider=FiveQueryModel())
    decision_id = ready(repository, engine)

    result = engine.run(decision_id)

    assert result.outputs["planning"]["queries"] == ["baseline", "risk", "cost"]
    assert [item.query for item in result.research_queries] == [
        "baseline",
        "risk",
        "cost",
    ]

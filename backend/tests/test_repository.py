import pytest
from sqlalchemy import create_engine

from app.schemas import BusinessBaseline, DecisionCreate, DecisionStatus, EvidenceCard
from app.providers.base import ProviderCallContext
from app.repository import DecisionRepository
from app.state_machine import InvalidTransition


def sample_decision() -> DecisionCreate:
    return DecisionCreate(
        question="Should we pilot AI support before a full rollout?",
        time_window="14 days",
        budget_limit=8000,
        primary_goal="Reduce repetitive support workload safely",
    )


def sample_evidence() -> EvidenceCard:
    return EvidenceCard(
        title="A source title",
        summary="A source-backed summary.",
        source_url="https://example.com/source",
        stance="supports",
        reliability="high",
    )


def test_repository_round_trips_decision_evidence_event_and_review(tmp_path):
    repository = DecisionRepository(tmp_path / "veriplan.db")
    decision = repository.create(sample_decision())

    repository.append_event(
        decision.id,
        stage="planning",
        status="started",
        summary="Planning research tasks",
    )
    repository.save_evidence(decision.id, sample_evidence())
    repository.save_evidence(decision.id, sample_evidence())
    for status in (
            DecisionStatus.clarifying,
            DecisionStatus.awaiting_confirmation,
            DecisionStatus.planning,
        DecisionStatus.researching,
        DecisionStatus.analyzing,
        DecisionStatus.challenging,
        DecisionStatus.delivering,
        DecisionStatus.awaiting_review,
    ):
        repository.update_status(decision.id, status)
    repository.apply_review(decision.id, action="accepted", note="Pilot approved")

    recovered = DecisionRepository(tmp_path / "veriplan.db").get(decision.id)

    assert recovered.status is DecisionStatus.accepted
    assert len(recovered.evidence) == 1
    assert recovered.evidence[0].is_demo is True
    assert recovered.evidence[0].source_url == "https://example.com/source"
    assert recovered.events[0].stage == "planning"
    assert recovered.review_note == "Pilot approved"


def test_repository_round_trips_real_evidence_provenance(tmp_path):
    path = tmp_path / "veriplan.db"
    repository = DecisionRepository(path)
    decision = repository.create(sample_decision())
    repository.save_evidence(
        decision.id,
        sample_evidence().model_copy(update={"is_demo": False}),
    )
    repository._engine.dispose()

    recovered = DecisionRepository(path).get(decision.id)

    assert recovered.evidence[0].is_demo is False


def test_repository_round_trips_a_frozen_business_baseline_snapshot(tmp_path):
    repository = DecisionRepository(tmp_path / "veriplan.db")
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

    created = repository.create(payload)
    payload.business_baseline.monthly_ticket_volume = 9_999
    recovered = repository.get(created.id)

    assert recovered.business_baseline.monthly_ticket_volume == 1_000
    assert recovered.baseline_analysis.is_calculable is True
    assert recovered.baseline_analysis.automatable_ticket_volume == 420
    assert recovered.baseline_analysis.monthly_hours_saved == 49
    assert recovered.baseline_analysis.estimated_monthly_net_savings == 1_160


def test_repository_adds_demo_provenance_to_legacy_evidence_without_data_loss(tmp_path):
    path = tmp_path / "legacy.db"
    legacy_engine = create_engine(f"sqlite:///{path}")
    with legacy_engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE evidence_cards (
                id INTEGER NOT NULL PRIMARY KEY,
                decision_id VARCHAR(36) NOT NULL,
                title VARCHAR(160) NOT NULL,
                summary TEXT NOT NULL,
                source_url TEXT NOT NULL,
                stance VARCHAR(16) NOT NULL,
                reliability VARCHAR(16) NOT NULL,
                FOREIGN KEY(decision_id) REFERENCES decisions (id)
            )
            """
        )
    legacy_engine.dispose()

    repository = DecisionRepository(path)
    decision = repository.create(sample_decision())
    with repository._engine.begin() as connection:
        connection.exec_driver_sql(
            """
            INSERT INTO evidence_cards
                (decision_id, title, summary, source_url, stance, reliability)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                decision.id,
                "Legacy demo evidence",
                "Synthetic evidence saved before provenance was persisted.",
                "https://demo.invalid/legacy",
                "context",
                "low",
            ),
        )
    repository._engine.dispose()

    recovered = DecisionRepository(path).get(decision.id)

    assert recovered.evidence[0].title == "Legacy demo evidence"
    assert recovered.evidence[0].is_demo is True


def test_repository_cannot_bypass_the_workflow_state_machine(tmp_path):
    repository = DecisionRepository(tmp_path / "veriplan.db")
    decision = repository.create(sample_decision())

    with pytest.raises(InvalidTransition):
        repository.update_status(decision.id, DecisionStatus.accepted)


def test_recovered_event_timestamps_remain_explicitly_utc(tmp_path):
    repository = DecisionRepository(tmp_path / 'db')
    decision = repository.create(sample_decision())
    repository.append_event(decision.id, stage='clarifying', status='started', summary='Demo')
    recovered = DecisionRepository(tmp_path / 'db').get(decision.id)
    assert recovered.events[0].created_at.utcoffset() is not None
    assert recovered.events[0].model_dump(mode='json')['created_at'].endswith('Z')


def test_retry_cannot_advance_to_any_stage_other_than_recorded_failure(tmp_path):
    repository = DecisionRepository(tmp_path / 'db')
    decision = repository.create(sample_decision())
    repository.update_status(decision.id, DecisionStatus.clarifying)
    repository.mark_failed(decision.id, 'clarifying')
    repository.update_status(decision.id, DecisionStatus.retrying)
    with pytest.raises(ValueError):
        repository.update_status(decision.id, DecisionStatus.delivering)
    repository.update_status(decision.id, DecisionStatus.clarifying)


def test_repository_round_trips_live_mode_queries_and_evidence_owner(tmp_path):
    repository = DecisionRepository(tmp_path / "db")
    decision = repository.create(sample_decision(), mode="live")
    queries = repository.sync_research_queries(
        decision.id,
        ["baseline", "risk", "cost"],
    )
    running = repository.start_research_query(decision.id, queries[0].id)
    evidence_id = repository.save_evidence(
        decision.id,
        sample_evidence().model_copy(update={"is_demo": False}),
        research_query_id=queries[0].id,
    )
    repository.complete_research_query(
        decision.id,
        queries[0].id,
        evidence_count=1,
    )

    recovered = DecisionRepository(tmp_path / "db").get(decision.id)

    assert running.attempt_count == 1
    assert evidence_id is not None
    assert recovered.mode == "live"
    assert recovered.research_queries[0].status == "succeeded"
    assert recovered.research_queries[0].evidence_count == 1
    assert recovered.evidence[0].research_query_id == queries[0].id


def test_running_query_is_recovered_as_failed_without_automatic_attempt(tmp_path):
    path = tmp_path / "db"
    repository = DecisionRepository(path)
    decision = repository.create(sample_decision(), mode="live")
    query = repository.sync_research_queries(decision.id, ["baseline"])[0]
    repository.start_research_query(decision.id, query.id)
    repository._engine.dispose()

    restarted = DecisionRepository(path)
    restarted.recover_running_research_queries("live")
    recovered = restarted.get(decision.id).research_queries[0]

    assert recovered.status == "failed"
    assert recovered.last_error_code == "interrupted"
    assert recovered.attempt_count == 1


def test_legacy_decision_defaults_to_demo_mode(tmp_path):
    path = tmp_path / "legacy.db"
    legacy_engine = create_engine(f"sqlite:///{path}")
    with legacy_engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE decisions (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                question TEXT NOT NULL,
                time_window VARCHAR(80) NOT NULL,
                budget_limit INTEGER NOT NULL,
                primary_goal VARCHAR(200) NOT NULL,
                status VARCHAR(32) NOT NULL,
                review_note TEXT,
                output_json TEXT NOT NULL,
                created_at DATETIME NOT NULL
            )
            """
        )
        connection.exec_driver_sql(
            """
            INSERT INTO decisions
                (id, question, time_window, budget_limit, primary_goal,
                 status, review_note, output_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-decision",
                "Should we pilot AI support before a full rollout?",
                "14 days",
                8000,
                "Reduce repetitive support workload safely",
                "draft",
                None,
                "{}",
                "2026-09-01 00:00:00",
            ),
        )
    legacy_engine.dispose()

    recovered = DecisionRepository(path).get("legacy-decision")

    assert recovered.mode == "demo"
    assert recovered.research_queries == []
    assert recovered.business_baseline == BusinessBaseline()
    assert recovered.baseline_analysis.known_field_count == 0
    assert len(recovered.baseline_analysis.collection_tasks) == 4


def test_provider_call_ledger_is_append_only_and_redacted(tmp_path):
    repository = DecisionRepository(tmp_path / "db")
    decision = repository.create(sample_decision(), mode="live")
    context = ProviderCallContext(
        decision_id=decision.id,
        logical_operation="planning",
        stage="planning",
    )
    call_id = repository.start_provider_attempt(
        context=context,
        provider="deepseek",
        attempt_number=1,
    )
    repository.finish_provider_attempt(
        call_id,
        status="failed",
        error_code="model_rate_limited",
    )

    calls = repository.list_provider_calls(decision.id)
    serialized = str(calls)
    assert calls[0]["status"] == "failed"
    assert calls[0]["error_code"] == "model_rate_limited"
    assert "request" not in serialized.lower()
    assert "authorization" not in serialized.lower()
    assert "response" not in serialized.lower()


def test_open_provider_call_is_recovered_without_contacting_provider(tmp_path):
    repository = DecisionRepository(tmp_path / "db")
    decision = repository.create(sample_decision(), mode="live")
    call_id = repository.start_provider_attempt(
        context=ProviderCallContext(
            decision_id=decision.id,
            logical_operation="researching",
            stage="researching",
        ),
        provider="tavily",
        attempt_number=1,
    )

    repository.recover_open_provider_calls("live")

    call = repository.list_provider_calls(decision.id)[0]
    assert call["id"] == call_id
    assert call["status"] == "failed"
    assert call["error_code"] == "interrupted"
    assert call["finished_at"] is not None

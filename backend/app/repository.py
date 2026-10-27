"""SQLite persistence boundary for complete VeriPlan decision snapshots."""

import json
from datetime import UTC, datetime
from typing import Any, Literal
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, func, inspect, select, text, update
from sqlalchemy.orm import Session, sessionmaker, selectinload

from app.models import (
    Base,
    DecisionRecord,
    EvidenceRecord,
    ProviderCallRecord,
    ResearchQueryRecord,
    UserRecord,
    WorkflowEventRecord,
)
from app.baseline import analyze_business_baseline
from app.schemas import (
    BusinessBaseline,
    InvalidInput,
    Assumption,
    OutcomeRequest,
    RetrospectiveCreate,
    DecisionCreate,
    DecisionSnapshot,
    DecisionStatus,
    EvidenceCard,
    ResearchQuery,
    ResearchQueryStatus,
    WorkflowEvent,
)
from app.state_machine import transition
from app.providers.base import ProviderCallContext


_ALL_OWNERS = object()


class DecisionRepository:
    """Persists data only; callers retain ownership of workflow orchestration."""

    def __init__(self, database_path: Path):
        url = str(database_path) if str(database_path).startswith("sqlite:") else f"sqlite:///{database_path}"
        self._engine = create_engine(url)
        Base.metadata.create_all(self._engine)
        self._migrate_schema_columns()
        self._sessions = sessionmaker(self._engine, expire_on_commit=False)

    def _migrate_schema_columns(self) -> None:
        inspector = inspect(self._engine)
        decision_columns = {
            column["name"] for column in inspector.get_columns("decisions")
        }
        evidence_columns = {
            column["name"] for column in inspector.get_columns("evidence_cards")
        }
        statements: list[str] = []
        provider_columns = {column["name"] for column in inspector.get_columns("provider_calls")}
        for column, size in (("profile", 32), ("model", 128)):
            if column not in provider_columns:
                statements.append(f"ALTER TABLE provider_calls ADD COLUMN {column} VARCHAR({size})")
        if "incomplete_reason" not in provider_columns:
            statements.append("ALTER TABLE provider_calls ADD COLUMN incomplete_reason VARCHAR(32)")
        if "mode" not in decision_columns:
            statements.append(
                "ALTER TABLE decisions ADD COLUMN mode VARCHAR(8) NOT NULL DEFAULT 'demo'"
            )
        if "business_baseline_json" not in decision_columns:
            statements.append(
                "ALTER TABLE decisions ADD COLUMN business_baseline_json TEXT NOT NULL DEFAULT '{}'"
            )
        additions = {
            "owner_id": "INTEGER",
            "scenario": "VARCHAR(32) NOT NULL DEFAULT 'ai_tool_pilot'",
            "horizon_days": "INTEGER NOT NULL DEFAULT 14",
            "known_risks_json": "TEXT NOT NULL DEFAULT '[]'",
            "assumptions_json": "TEXT NOT NULL DEFAULT '[]'",
            "objection_labels_json": "TEXT NOT NULL DEFAULT '{}'",
            "outcomes_json": "TEXT NOT NULL DEFAULT '[]'",
            "is_retrospective": "BOOLEAN NOT NULL DEFAULT 0",
        }
        for column, definition in additions.items():
            if column not in decision_columns:
                statements.append(f"ALTER TABLE decisions ADD COLUMN {column} {definition}")
        if "is_demo" not in evidence_columns:
            statements.append(
                "ALTER TABLE evidence_cards ADD COLUMN is_demo BOOLEAN NOT NULL DEFAULT 1"
            )
        if "research_query_id" not in evidence_columns:
            statements.append(
                "ALTER TABLE evidence_cards ADD COLUMN research_query_id INTEGER"
            )
        if statements:
            with self._engine.begin() as connection:
                for statement in statements:
                    connection.execute(text(statement))

    def create(
        self,
        payload: DecisionCreate,
        *,
        mode: Literal["demo", "live"] = "demo",
        owner_id: int | None = None,
    ) -> DecisionSnapshot:
        with self._sessions.begin() as session:
            record = DecisionRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                **payload.model_dump(exclude={"business_baseline", "known_risks", "assumptions"}),
                known_risks_json=json.dumps(payload.known_risks),
                assumptions_json=json.dumps([
                    {**item.model_dump(), "id": f"A{index}"}
                    for index, item in enumerate(payload.assumptions, 1)
                ]),
                business_baseline_json=payload.business_baseline.model_dump_json(),
                status=DecisionStatus.draft.value,
                mode=mode,
                review_note=None,
                output_json="{}",
                created_at=datetime.now(UTC),
            )
            session.add(record)
            session.flush()
            return self._snapshot(record)

    def append_event(self, decision_id: str, *, stage: str, status: str, summary: str) -> None:
        with self._sessions.begin() as session:
            self._require(session, decision_id)
            session.add(
                WorkflowEventRecord(
                    decision_id=decision_id,
                    stage=stage,
                    status=status,
                    summary=summary,
                    created_at=datetime.now(UTC),
                )
            )

    def save_evidence(
        self,
        decision_id: str,
        evidence: EvidenceCard,
        *,
        research_query_id: int | None = None,
    ) -> str | None:
        with self._sessions.begin() as session:
            self._require(session, decision_id)
            if research_query_id is not None:
                query = session.get(ResearchQueryRecord, research_query_id)
                if query is None or query.decision_id != decision_id:
                    raise ValueError("Research query does not belong to decision")
            existing = session.scalar(select(EvidenceRecord).where(EvidenceRecord.decision_id == decision_id, EvidenceRecord.source_url == evidence.source_url))
            if existing is not None:
                return None
            record = EvidenceRecord(
                decision_id=decision_id,
                research_query_id=research_query_id,
                **evidence.model_dump(exclude={"id", "research_query_id"}),
            )
            session.add(record)
            session.flush()
            return str(record.id)

    def sync_research_queries(
        self,
        decision_id: str,
        queries: list[str],
        *,
        max_queries: int = 3,
    ) -> list[ResearchQuery]:
        if max_queries not in (3, 5) or len(queries) > max_queries or len(set(queries)) != len(queries):
            raise ValueError("Research queries must be unique and within the query limit")
        with self._sessions.begin() as session:
            decision = self._require(session, decision_id)
            existing = list(
                session.scalars(
                    select(ResearchQueryRecord)
                    .where(ResearchQueryRecord.decision_id == decision_id)
                    .order_by(ResearchQueryRecord.ordinal)
                )
            )
            if existing:
                old_queries = [item.query for item in existing]
                if old_queries == queries:
                    return [self._research_query(item) for item in existing]
                if max_queries != 5 or queries[:len(existing)] != old_queries:
                    raise ValueError("Research queries are already initialized")
            now = datetime.now(UTC)
            records = [
                ResearchQueryRecord(
                    decision_id=decision.id,
                    ordinal=ordinal,
                    query=query,
                    status=ResearchQueryStatus.pending.value,
                    attempt_count=0,
                    last_error_code=None,
                    evidence_count=0,
                    created_at=now,
                    started_at=None,
                    finished_at=None,
                )
                for ordinal, query in enumerate(queries[len(existing):], start=len(existing))
            ]
            session.add_all(records)
            session.flush()
            return [self._research_query(item) for item in [*existing, *records]]

    def start_research_query(
        self,
        decision_id: str,
        query_id: int,
    ) -> ResearchQuery:
        with self._sessions.begin() as session:
            query = self._require_query(session, decision_id, query_id)
            if query.status not in {
                ResearchQueryStatus.pending.value,
                ResearchQueryStatus.failed.value,
            }:
                raise ValueError("Only pending or failed research queries can start")
            query.status = ResearchQueryStatus.running.value
            query.attempt_count += 1
            query.last_error_code = None
            query.started_at = datetime.now(UTC)
            query.finished_at = None
            session.flush()
            return self._research_query(query)

    def complete_research_query(
        self,
        decision_id: str,
        query_id: int,
        *,
        evidence_count: int,
    ) -> None:
        if evidence_count < 0:
            raise ValueError("Evidence count cannot be negative")
        with self._sessions.begin() as session:
            query = self._require_query(session, decision_id, query_id)
            if query.status != ResearchQueryStatus.running.value:
                raise ValueError("Only a running research query can complete")
            query.status = ResearchQueryStatus.succeeded.value
            query.evidence_count = evidence_count
            query.finished_at = datetime.now(UTC)

    def fail_research_query(
        self,
        decision_id: str,
        query_id: int,
        *,
        code: str,
    ) -> None:
        with self._sessions.begin() as session:
            query = self._require_query(session, decision_id, query_id)
            if query.status != ResearchQueryStatus.running.value:
                raise ValueError("Only a running research query can fail")
            query.status = ResearchQueryStatus.failed.value
            query.last_error_code = code
            query.finished_at = datetime.now(UTC)

    def recover_running_research_queries(
        self,
        mode: Literal["demo", "live"],
    ) -> None:
        with self._sessions.begin() as session:
            running = session.scalars(
                select(ResearchQueryRecord)
                .join(DecisionRecord)
                .where(
                    ResearchQueryRecord.status == ResearchQueryStatus.running.value,
                    DecisionRecord.mode == mode,
                )
            )
            now = datetime.now(UTC)
            for query in running:
                query.status = ResearchQueryStatus.failed.value
                query.last_error_code = "interrupted"
                query.finished_at = now

    def start_provider_attempt(
        self,
        *,
        context: ProviderCallContext,
        provider: str,
        attempt_number: int,
        profile: str | None = None,
        model: str | None = None,
    ) -> int:
        if attempt_number < 1:
            raise ValueError("Attempt number must be positive")
        with self._sessions.begin() as session:
            self._require(session, context.decision_id)
            if context.research_query_id is not None:
                self._require_query(
                    session,
                    context.decision_id,
                    context.research_query_id,
                )
            record = ProviderCallRecord(
                decision_id=context.decision_id,
                provider=provider,
                profile=profile,
                model=model,
                logical_operation=context.logical_operation,
                stage=context.stage,
                research_query_id=context.research_query_id,
                attempt_number=attempt_number,
                status="running",
                error_code=None,
                started_at=datetime.now(UTC),
                finished_at=None,
            )
            session.add(record)
            session.flush()
            return record.id

    def finish_provider_attempt(
        self,
        call_id: int,
        *,
        status: str,
        error_code: str | None = None,
        incomplete_reason: str | None = None,
    ) -> None:
        if status not in {"succeeded", "failed"}:
            raise ValueError("Provider attempt terminal status is invalid")
        with self._sessions.begin() as session:
            record = session.get(ProviderCallRecord, call_id)
            if record is None:
                raise KeyError(call_id)
            if record.status != "running":
                raise ValueError("Provider attempt is already finished")
            record.status = status
            record.error_code = error_code
            record.incomplete_reason = incomplete_reason if incomplete_reason in {"max_output_tokens", "content_filter", "unknown"} else None
            record.finished_at = datetime.now(UTC)

    def list_provider_calls(self, decision_id: str) -> list[dict[str, Any]]:
        with self._sessions() as session:
            self._require(session, decision_id)
            records = session.scalars(
                select(ProviderCallRecord)
                .where(ProviderCallRecord.decision_id == decision_id)
                .order_by(ProviderCallRecord.id)
            )
            return [
                {
                    "id": record.id,
                    "provider": record.provider,
                    "profile": record.profile,
                    "model": record.model,
                    "logical_operation": record.logical_operation,
                    "stage": record.stage,
                    "research_query_id": record.research_query_id,
                    "attempt_number": record.attempt_number,
                    "status": record.status,
                    "error_code": record.error_code,
                    "incomplete_reason": record.incomplete_reason,
                    "started_at": record.started_at,
                    "finished_at": record.finished_at,
                }
                for record in records
            ]

    def recover_open_provider_calls(
        self,
        mode: Literal["demo", "live"],
    ) -> None:
        with self._sessions.begin() as session:
            records = session.scalars(
                select(ProviderCallRecord)
                .join(DecisionRecord)
                .where(
                    ProviderCallRecord.status == "running",
                    DecisionRecord.mode == mode,
                )
            )
            now = datetime.now(UTC)
            for record in records:
                record.status = "failed"
                record.error_code = "interrupted"
                record.finished_at = now

    def save_stage_output(self, decision_id: str, stage: str, output: dict[str, Any]) -> None:
        with self._sessions.begin() as session:
            record = self._require(session, decision_id)
            outputs = json.loads(record.output_json)
            outputs[stage] = output
            record.output_json = json.dumps(outputs)

    def update_status(self, decision_id: str, status: DecisionStatus) -> None:
        """Persist only a transition the workflow state machine permits."""
        with self._sessions.begin() as session:
            record = self._require(session, decision_id)
            if record.status == "retrying" and status.value != json.loads(record.output_json).get("_failure", {}).get("stage"):
                raise ValueError("Retry must resume the stored failed stage")
            record.status = transition(DecisionStatus(record.status), status).value

    def apply_review(self, decision_id: str, *, action: str, note: str | None = None) -> None:
        with self._sessions.begin() as session:
            record = self._require(session, decision_id)
            record.status = transition(DecisionStatus(record.status), DecisionStatus(action)).value
            record.review_note = note

    def save_objection_labels(self, decision_id: str, labels: dict, *, mode: str) -> None:
        with self._sessions.begin() as session:
            record = self._require(session, decision_id)
            if record.mode != mode:
                raise ValueError("Decision mode does not match the current application mode")
            if record.status not in {"awaiting_review", "accepted", "revised", "deferred"}:
                raise ValueError("Objection labels require the review gate")
            objections = json.loads(record.output_json).get("challenging", {}).get("objections", [])
            if set(labels) - {item["id"] for item in objections}:
                raise InvalidInput("Unknown objection ID")
            record.objection_labels_json = json.dumps(json.loads(record.objection_labels_json) | labels)

    def save_outcome(self, decision_id: str, payload: OutcomeRequest, *, mode: str) -> None:
        from app.calibration import APPROVED, calculate_actuals
        with self._sessions.begin() as session:
            record = self._require(session, decision_id)
            if record.mode != mode:
                raise ValueError("Decision mode does not match the current application mode")
            if record.status not in APPROVED:
                raise ValueError("Outcomes require a completed human review")
            actuals = calculate_actuals([Assumption(**item) for item in json.loads(record.assumptions_json)], payload.actuals)
            outcomes = [item for item in json.loads(record.outcomes_json) if item['checkpoint'] != payload.checkpoint]
            outcomes.append(dict(checkpoint=payload.checkpoint, note=payload.note,
                                 recorded_at=datetime.now(UTC).isoformat(), actuals=actuals))
            record.outcomes_json = json.dumps(outcomes)

    def create_retrospective(self, payload: RetrospectiveCreate, *, mode: str = "demo",
                             seed_id: str | None = None, owner_id: int | None = None) -> DecisionSnapshot:
        from app.calibration import calculate_actuals
        assumptions = [Assumption(**item.model_dump(), id=f'A{index}') for index, item in enumerate(payload.assumptions, 1)]
        actuals = calculate_actuals(assumptions, payload.actuals)
        with self._sessions.begin() as session:
            record = DecisionRecord(
                id=seed_id or str(uuid4()), question=payload.question, scenario=payload.scenario,
                owner_id=owner_id,
                time_window='90 天', horizon_days=90, budget_limit=0, primary_goal='回溯校准',
                business_baseline_json='{}', known_risks_json='[]',
                assumptions_json=json.dumps([item.model_dump() for item in assumptions]),
                objection_labels_json='{}',
                outcomes_json=json.dumps([dict(checkpoint='custom', recorded_at=datetime.now(UTC).isoformat(),
                                               note=payload.note, actuals=actuals)]),
                is_retrospective=True, status='retrospective', mode=mode, review_note=None,
                output_json=json.dumps({'retrospective': dict(decision_date=payload.decision_date.isoformat(),
                                                              note=payload.note, is_synthetic=seed_id is not None)}),
                created_at=datetime.combine(payload.decision_date, datetime.min.time(), tzinfo=UTC) if seed_id else datetime.now(UTC),
            )
            session.add(record)
            session.flush()
            return self._snapshot(record)

    def list(self, *, owner_id=_ALL_OWNERS) -> list[DecisionSnapshot]:
        # Omission is reserved for internal recovery; explicit None selects legacy rows only.
        with self._sessions() as session:
            query = select(DecisionRecord).order_by(DecisionRecord.created_at.desc()).options(selectinload(DecisionRecord.evidence), selectinload(DecisionRecord.events), selectinload(DecisionRecord.research_queries))
            if owner_id is not _ALL_OWNERS:
                query = query.where(DecisionRecord.owner_id == owner_id)
            records = session.scalars(query).all()
            return [self._snapshot(record) for record in records]

    def owner_of(self, decision_id: str) -> int | None:
        with self._sessions() as session:
            row = session.execute(select(DecisionRecord.owner_id).where(DecisionRecord.id == decision_id)).one_or_none()
            if row is None:
                raise KeyError(decision_id)
            return row.owner_id

    def claim_legacy(self, username: str) -> int:
        with self._sessions.begin() as session:
            user = session.scalar(select(UserRecord).where(func.lower(UserRecord.username) == username.strip().lower()))
            if user is None:
                raise ValueError("用户不存在")
            result = session.execute(update(DecisionRecord).where(DecisionRecord.owner_id.is_(None)).values(owner_id=user.id))
            return result.rowcount

    def mark_failed(self, decision_id: str, stage: str, code: str = "stage_failed", *, incomplete_reason: str | None = None) -> None:
        with self._sessions.begin() as session:
            record = self._require(session, decision_id)
            record.status = transition(DecisionStatus(record.status), DecisionStatus.failed).value
            outputs = json.loads(record.output_json)
            outputs["_failure"] = {"stage": stage, "code": code, "message": "运行中断，请重试当前阶段。" if code == "interrupted" else "阶段执行失败，请重试；已完成输出已保留。"}
            if incomplete_reason in {"max_output_tokens", "content_filter", "unknown"}:
                outputs["_failure"]["incomplete_reason"] = incomplete_reason
            record.output_json = json.dumps(outputs, ensure_ascii=False)
            session.add(WorkflowEventRecord(decision_id=decision_id, stage=stage, status="failed", summary=outputs["_failure"]["message"], created_at=datetime.now(UTC)))

    def complete_stage(self, decision_id: str, stage: str, output: dict, target: DecisionStatus) -> None:
        # Commit output, completion event and advancement together, so restart cannot
        # repeat an already committed stage or omit its completion event.
        with self._sessions.begin() as session:
            record = self._require(session, decision_id)
            record.status = transition(DecisionStatus(record.status), target).value
            outputs = json.loads(record.output_json)
            outputs[stage] = output
            outputs.pop("_failure", None)
            record.output_json = json.dumps(outputs)
            session.add(WorkflowEventRecord(decision_id=decision_id, stage=stage, status="completed", summary=output["summary"], created_at=datetime.now(UTC)))

    def get(self, decision_id: str) -> DecisionSnapshot:
        with self._sessions() as session:
            record = session.scalar(
                select(DecisionRecord)
                .where(DecisionRecord.id == decision_id)
                .options(selectinload(DecisionRecord.evidence), selectinload(DecisionRecord.events), selectinload(DecisionRecord.research_queries))
            )
            if record is None:
                raise KeyError(decision_id)
            return self._snapshot(record)

    @staticmethod
    def _require(session: Session, decision_id: str) -> DecisionRecord:
        record = session.get(DecisionRecord, decision_id)
        if record is None:
            raise KeyError(decision_id)
        return record

    @staticmethod
    def _require_query(
        session: Session,
        decision_id: str,
        query_id: int,
    ) -> ResearchQueryRecord:
        query = session.get(ResearchQueryRecord, query_id)
        if query is None or query.decision_id != decision_id:
            raise ValueError("Research query does not belong to decision")
        return query

    @staticmethod
    def _research_query(record: ResearchQueryRecord) -> ResearchQuery:
        def with_utc(value: datetime | None) -> datetime | None:
            if value is None or value.tzinfo is not None:
                return value
            return value.replace(tzinfo=UTC)

        return ResearchQuery(
            id=record.id,
            ordinal=record.ordinal,
            query=record.query,
            status=ResearchQueryStatus(record.status),
            attempt_count=record.attempt_count,
            last_error_code=record.last_error_code,
            evidence_count=record.evidence_count,
            created_at=with_utc(record.created_at),
            started_at=with_utc(record.started_at),
            finished_at=with_utc(record.finished_at),
        )

    @staticmethod
    def _snapshot(record: DecisionRecord) -> DecisionSnapshot:
        business_baseline = BusinessBaseline.model_validate(
            json.loads(record.business_baseline_json)
        )
        return DecisionSnapshot(
            mode=record.mode,
            scenario=record.scenario,
            horizon_days=record.horizon_days,
            known_risks=json.loads(record.known_risks_json),
            assumptions=json.loads(record.assumptions_json),
            objection_labels=json.loads(record.objection_labels_json),
            outcomes=json.loads(record.outcomes_json),
            is_retrospective=record.is_retrospective,
            research_queries=[
                DecisionRepository._research_query(item)
                for item in record.research_queries
            ],
            id=record.id,
            question=record.question,
            time_window=record.time_window,
            budget_limit=record.budget_limit,
            primary_goal=record.primary_goal,
            business_baseline=business_baseline,
            baseline_analysis=analyze_business_baseline(business_baseline),
            status=DecisionStatus(record.status),
            evidence=[
                EvidenceCard(
                    id=str(item.id),
                    research_query_id=item.research_query_id,
                    is_demo=item.is_demo,
                    title=item.title,
                    summary=item.summary,
                    source_url=item.source_url,
                    stance=item.stance,
                    reliability=item.reliability,
                )
                for item in record.evidence
            ],
            events=[
                WorkflowEvent(
                    stage=item.stage,
                    status=item.status,
                    summary=item.summary,
                    created_at=item.created_at.replace(tzinfo=UTC) if item.created_at.tzinfo is None else item.created_at,
                )
                for item in record.events
            ],
            failure=json.loads(record.output_json).get("_failure"),
            outputs={key: value for key, value in json.loads(record.output_json).items() if not key.startswith("_")},
            memo=json.loads(record.output_json).get("delivering"),
            review_note=record.review_note,
        )

"""SQLAlchemy tables; API code never returns these ORM rows directly."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class DecisionRecord(Base):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    time_window: Mapped[str] = mapped_column(String(80))
    budget_limit: Mapped[int] = mapped_column(Integer)
    primary_goal: Mapped[str] = mapped_column(String(200))
    business_baseline_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default=text("'{}'")
    )
    scenario: Mapped[str] = mapped_column(String(32), default="ai_tool_pilot", server_default="ai_tool_pilot")
    horizon_days: Mapped[int] = mapped_column(Integer, default=14, server_default="14")
    known_risks_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    assumptions_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    objection_labels_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    outcomes_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    is_retrospective: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    status: Mapped[str] = mapped_column(String(32))
    mode: Mapped[str] = mapped_column(
        String(8), nullable=False, default="demo", server_default=text("'demo'")
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence: Mapped[list["EvidenceRecord"]] = relationship(
        back_populates="decision", cascade="all, delete-orphan", order_by="EvidenceRecord.id"
    )
    events: Mapped[list["WorkflowEventRecord"]] = relationship(
        back_populates="decision", cascade="all, delete-orphan", order_by="WorkflowEventRecord.created_at"
    )
    research_queries: Mapped[list["ResearchQueryRecord"]] = relationship(
        back_populates="decision",
        cascade="all, delete-orphan",
        order_by="ResearchQueryRecord.ordinal",
    )
    provider_calls: Mapped[list["ProviderCallRecord"]] = relationship(
        back_populates="decision",
        cascade="all, delete-orphan",
        order_by="ProviderCallRecord.id",
    )


class ResearchQueryRecord(Base):
    __tablename__ = "research_queries"
    __table_args__ = (
        UniqueConstraint("decision_id", "ordinal"),
        UniqueConstraint("decision_id", "query"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    query: Mapped[str] = mapped_column(String(400))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision: Mapped[DecisionRecord] = relationship(back_populates="research_queries")


class EvidenceRecord(Base):
    __tablename__ = "evidence_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.id"), index=True)
    research_query_id: Mapped[int | None] = mapped_column(
        ForeignKey("research_queries.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    stance: Mapped[str] = mapped_column(String(16))
    reliability: Mapped[str] = mapped_column(String(16))
    is_demo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )
    decision: Mapped[DecisionRecord] = relationship(back_populates="evidence")


class ProviderCallRecord(Base):
    __tablename__ = "provider_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.id"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    logical_operation: Mapped[str] = mapped_column(String(64))
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    research_query_id: Mapped[int | None] = mapped_column(
        ForeignKey("research_queries.id"), nullable=True, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision: Mapped[DecisionRecord] = relationship(back_populates="provider_calls")


class WorkflowEventRecord(Base):
    __tablename__ = "workflow_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    decision_id: Mapped[str] = mapped_column(ForeignKey("decisions.id"), index=True)
    stage: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decision: Mapped[DecisionRecord] = relationship(back_populates="events")

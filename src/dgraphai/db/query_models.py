"""
Saved query and workflow DB models.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey,
    Integer, JSON, String, Text, UniqueConstraint, Index, Enum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.dgraphai.db.models import Base


def now_utc():
    return datetime.now(timezone.utc)


# ── Saved Queries (Graph Control) ─────────────────────────────────────────────

class SavedQuery(Base):
    """
    A named, reusable Cypher query — like Wiz Graph Control.
    Can be used as a data view, shared within a tenant, scheduled for export.
    """
    __tablename__ = "saved_queries"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id   = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    created_by  = Column(UUID(as_uuid=True), ForeignKey("users.id",   ondelete="SET NULL"))
    name        = Column(String(256), nullable=False)
    description = Column(Text)
    cypher      = Column(Text, nullable=False)
    params      = Column(JSON, default=dict)       # default parameter values
    tags        = Column(JSON, default=list)        # ["security", "pii", "ai-training"]
    is_public   = Column(Boolean, default=False)    # visible to all users in tenant
    is_pinned   = Column(Boolean, default=False)    # pinned to dashboard
    run_count   = Column(Integer, default=0)
    last_run_at = Column(DateTime(timezone=True))
    created_at  = Column(DateTime(timezone=True), default=now_utc)
    updated_at  = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    # Dataset export config
    export_format   = Column(String(32))   # jsonl | csv | parquet | none
    export_schedule = Column(String(64))   # cron expression or null
    export_destination = Column(JSON)      # {type: "s3", bucket: "...", prefix: "..."}

    exports     = relationship("QueryExport", back_populates="query", cascade="all, delete")

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tenant_query_name"),
        Index("ix_saved_queries_tenant", "tenant_id"),
    )


class QueryExport(Base):
    """Record of a saved query export run."""
    __tablename__ = "query_exports"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_id    = Column(UUID(as_uuid=True), ForeignKey("saved_queries.id", ondelete="CASCADE"), nullable=False)
    tenant_id   = Column(UUID(as_uuid=True), nullable=False)
    triggered_by = Column(String(32))      # "manual" | "schedule" | "api"
    status      = Column(String(32), default="pending")  # pending|running|complete|error
    row_count   = Column(Integer)
    file_size_bytes = Column(Integer)
    output_uri  = Column(Text)             # s3://... or local path
    error       = Column(Text)
    started_at  = Column(DateTime(timezone=True), default=now_utc)
    completed_at = Column(DateTime(timezone=True))

    query       = relationship("SavedQuery", back_populates="exports")


# ── Approval Workflows ────────────────────────────────────────────────────────

WORKFLOW_TRIGGER_TYPES = ("manual", "query_result", "schedule", "threshold")
ACTION_ITEM_TYPES      = ("move", "delete", "rename", "tag", "notify", "webhook")
APPROVAL_STATUSES      = ("pending", "approved", "rejected", "expired", "cancelled")

class WorkflowTemplate(Base):
    """
    Visual workflow definition for filesystem actions.
    Defines the steps, approvers, conditions, and actions.
    """
    __tablename__ = "workflow_templates"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id   = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    created_by  = Column(UUID(as_uuid=True))
    name        = Column(String(256), nullable=False)
    description = Column(Text)
    is_active   = Column(Boolean, default=True)

    # Trigger: what starts this workflow
    trigger_type  = Column(Enum(*WORKFLOW_TRIGGER_TYPES, name="workflow_trigger"), default="manual")
    trigger_config = Column(JSON, default=dict)
    # manual:        {}
    # query_result:  {"query_id": "...", "condition": "row_count > 0"}
    # schedule:      {"cron": "0 9 * * 1"}
    # threshold:     {"metric": "pii_file_count", "operator": ">", "value": 100}

    # Steps: ordered list of step definitions
    steps       = Column(JSON, default=list)
    # Each step: {
    #   "id": "step_1",
    #   "type": "approval" | "action" | "notify" | "condition",
    #   "name": "Security team approval",
    #   "config": {
    #     // approval: {"approvers": ["user_id_1"], "any_of": true, "timeout_hours": 48}
    #     // action:   {"action_type": "move", "params": {...}, "dry_run": false}
    #     // notify:   {"channels": ["email", "slack"], "message": "..."}
    #     // condition: {"expression": "approval_count >= 2"}
    #   }
    # }

    created_at  = Column(DateTime(timezone=True), default=now_utc)
    updated_at  = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    runs        = relationship("WorkflowRun", back_populates="template", cascade="all, delete")

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tenant_workflow_name"),
    )


class WorkflowRun(Base):
    """A running instance of a workflow template."""
    __tablename__ = "workflow_runs"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id  = Column(UUID(as_uuid=True), ForeignKey("workflow_templates.id", ondelete="CASCADE"), nullable=False)
    tenant_id    = Column(UUID(as_uuid=True), nullable=False)
    triggered_by = Column(String(32))
    triggered_by_user = Column(UUID(as_uuid=True))
    status       = Column(String(32), default="pending")  # pending|running|complete|rejected|error
    current_step = Column(Integer, default=0)
    context      = Column(JSON, default=dict)   # data passed between steps
    # e.g. {"files": [...], "query_results": [...], "approvals": {...}}
    result       = Column(JSON)
    error        = Column(Text)
    started_at   = Column(DateTime(timezone=True), default=now_utc)
    completed_at = Column(DateTime(timezone=True))

    template     = relationship("WorkflowTemplate", back_populates="runs")
    approvals    = relationship("ApprovalRequest", back_populates="run", cascade="all, delete")


class ApprovalRequest(Base):
    """An approval gate within a workflow run."""
    __tablename__ = "approval_requests"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id      = Column(UUID(as_uuid=True), ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False)
    tenant_id   = Column(UUID(as_uuid=True), nullable=False)
    step_id     = Column(String(64))
    step_name   = Column(String(256))
    description = Column(Text)               # human-readable summary of what needs approval
    context     = Column(JSON, default=dict) # files/actions that need approval
    status      = Column(Enum(*APPROVAL_STATUSES, name="approval_status"), default="pending")
    approver_id = Column(UUID(as_uuid=True))
    decision_note = Column(Text)
    expires_at  = Column(DateTime(timezone=True))
    decided_at  = Column(DateTime(timezone=True))
    created_at  = Column(DateTime(timezone=True), default=now_utc)

    run         = relationship("WorkflowRun", back_populates="approvals")

    __table_args__ = (
        Index("ix_approval_requests_run", "run_id", "status"),
    )

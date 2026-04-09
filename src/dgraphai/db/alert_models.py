"""
Alert and compliance report DB models.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.dgraphai.db.models import Base

def now_utc(): return datetime.now(timezone.utc)

ALERT_SEVERITIES = ("critical", "high", "medium", "low", "info")
ALERT_STATUSES   = ("active", "acknowledged", "resolved", "suppressed")
DELIVERY_CHANNELS = ("email", "webhook", "slack", "pagerduty", "siem")

class AlertRule(Base):
    """
    A named alert rule that watches the graph for conditions.
    Evaluated on a schedule or triggered by graph change events.
    """
    __tablename__ = "alert_rules"
    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id     = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name          = Column(String(256), nullable=False)
    description   = Column(Text)
    severity      = Column(Enum(*ALERT_SEVERITIES, name="alert_severity"), default="medium")
    is_active     = Column(Boolean, default=True)

    # Condition: Cypher query that returns rows when alert should fire
    # Alert fires when row_count > 0 (or matches threshold)
    cypher          = Column(Text, nullable=False)
    cypher_params   = Column(JSON, default=dict)
    threshold_count = Column(Integer, default=1)  # fire when results >= threshold

    # Schedule: how often to evaluate
    eval_schedule   = Column(String(64), default="0 * * * *")  # hourly cron
    last_evaluated  = Column(DateTime(timezone=True))
    last_fired_at   = Column(DateTime(timezone=True))

    # Delivery
    channels        = Column(JSON, default=list)  # [{type, config}]
    # e.g. [{"type": "email", "to": "security@co.com"},
    #        {"type": "webhook", "url": "https://..."},
    #        {"type": "slack", "channel": "#alerts"}]
    message_template = Column(Text)  # Jinja2 template for alert message

    # Suppression
    suppress_until  = Column(DateTime(timezone=True))  # snooze
    cooldown_minutes = Column(Integer, default=60)      # min time between firings

    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    alerts     = relationship("Alert", back_populates="rule", cascade="all, delete")


class Alert(Base):
    """A fired alert instance."""
    __tablename__ = "alerts"
    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id       = Column(UUID(as_uuid=True), ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False)
    tenant_id     = Column(UUID(as_uuid=True), nullable=False)
    severity      = Column(Enum(*ALERT_SEVERITIES, name="alert_severity2"), default="medium")
    status        = Column(Enum(*ALERT_STATUSES, name="alert_status"), default="active")
    title         = Column(String(512))
    message       = Column(Text)
    context       = Column(JSON, default=dict)  # query results that triggered the alert
    row_count     = Column(Integer)
    acknowledged_by = Column(UUID(as_uuid=True))
    acknowledged_at = Column(DateTime(timezone=True))
    resolved_at   = Column(DateTime(timezone=True))
    fired_at      = Column(DateTime(timezone=True), default=now_utc)
    rule          = relationship("AlertRule", back_populates="alerts")


class ComplianceReport(Base):
    """A generated compliance report."""
    __tablename__ = "compliance_reports"
    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id     = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    report_type   = Column(String(64), nullable=False)
    # gdpr_data_inventory | hipaa_phi_inventory | soc2_evidence |
    # pii_exposure | eol_software | secrets_exposure | certificate_expiry
    title         = Column(String(256))
    status        = Column(String(32), default="pending")  # pending|running|complete|error
    format        = Column(String(16), default="pdf")  # pdf | json | csv
    output_uri    = Column(Text)
    generated_by  = Column(UUID(as_uuid=True))
    row_count     = Column(Integer)
    findings      = Column(JSON, default=dict)  # summary counts
    error         = Column(Text)
    generated_at  = Column(DateTime(timezone=True), default=now_utc)
    completed_at  = Column(DateTime(timezone=True))

"""Connector configuration DB models."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.dgraphai.db.models import Base

def now_utc(): return datetime.now(timezone.utc)


class Connector(Base):
    """
    A configured data source connector.
    Stores encrypted credentials, routing preference, and live health metrics.
    """
    __tablename__ = "connectors"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id       = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name            = Column(String(256), nullable=False)
    description     = Column(Text)
    connector_type  = Column(String(64), nullable=False)  # aws-s3 | azure-blob | smb | nfs | sharepoint | gcs | local
    is_active       = Column(Boolean, default=True)
    config          = Column(JSON, default=dict)   # encrypted connection params
    tags            = Column(JSON, default=list)

    # Routing: which scanner agent proxies this connection
    # None = direct connection from backend (for cloud connectors)
    scanner_agent_id = Column(UUID(as_uuid=True), ForeignKey("scanner_agents.id", ondelete="SET NULL"), nullable=True)
    routing_mode    = Column(String(32), default="direct")  # direct | agent | auto

    # Health metrics — updated after each scan
    last_scan_at        = Column(DateTime(timezone=True))
    last_scan_status    = Column(String(32))   # success | error | warning | never
    last_scan_duration_secs = Column(Float)
    last_scan_files     = Column(Integer, default=0)
    last_scan_errors    = Column(Integer, default=0)
    last_scan_error_msg = Column(Text)
    total_files_indexed = Column(Integer, default=0)
    avg_throughput_fps  = Column(Float)        # files per second
    last_test_at        = Column(DateTime(timezone=True))
    last_test_result    = Column(Boolean)
    last_test_msg       = Column(Text)

    created_at      = Column(DateTime(timezone=True), default=now_utc)
    updated_at      = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    created_by      = Column(UUID(as_uuid=True))

    scanner_agent   = relationship("ScannerAgent", foreign_keys=[scanner_agent_id])

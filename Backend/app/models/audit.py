from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, DateTime, ForeignKey, 
    Text, Boolean, JSON, Index
)
from app.core.database import Base
from app.models.organization import generate_uuid, utc_now


class AuditEvent(Base):
    """
    Tamper-evident audit log for security, compliance, and regulatory review.
    """
    __tablename__ = "audit_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organisation_id = Column(String(36), nullable=True)
    facility_id = Column(String(36), nullable=True, index=True)
    actor_id = Column(String(64), nullable=True, index=True)
    action = Column(String(64), nullable=False, index=True) # e.g. APPROVE_PROPOSAL, RESERVE_STOCK, DISPATCH_PACKAGE, RECEIVE_PACKAGE, RECONCILE_DISCREPANCY
    entity_type = Column(String(64), nullable=False, index=True) # PROPOSAL, TRANSFER, INVENTORY, LABEL
    entity_id = Column(String(64), nullable=False, index=True)
    before_state = Column(JSON, nullable=True)
    after_state = Column(JSON, nullable=True)
    reason = Column(Text, nullable=True)
    correlation_id = Column(String(64), nullable=True, index=True)  # proposal_id / transfer_id / workflow_id
    created_at = Column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (
        Index("ix_audit_entity_time", "entity_type", "entity_id", "created_at"),
        Index("ix_audit_correlation", "correlation_id"),
    )


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    facility_id = Column(String(36), ForeignKey("facilities.id"), nullable=False, index=True)
    source_type = Column(String(64), nullable=False) # CSV_IMPORT, ERP_SYNC, SYNTHETIC_SEED
    filename = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="PROCESSING") # PROCESSING, COMPLETED, FAILED
    row_count = Column(Integer, nullable=False, default=0)
    accepted_count = Column(Integer, nullable=False, default=0)
    rejected_count = Column(Integer, nullable=False, default=0)
    error_summary = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)


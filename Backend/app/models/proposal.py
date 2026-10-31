from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, DateTime, ForeignKey, 
    Text, Boolean, JSON, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.organization import generate_uuid, utc_now


class TransferProposal(Base):
    """
    Evidence-backed redistribution proposal generated deterministically.
    Requires dual human approval (source + destination) referencing exact proposal_version.
    """
    __tablename__ = "transfer_proposals"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    source_facility_id = Column(String(36), ForeignKey("facilities.id"), nullable=False, index=True)
    destination_facility_id = Column(String(36), ForeignKey("facilities.id"), nullable=False, index=True)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False, index=True)
    proposed_quantity = Column(Integer, nullable=False)
    unit = Column(String(32), nullable=False, default="UNIT")
    
    # Status lifecycle:
    # PROPOSED, PENDING_SOURCE_APPROVAL, PENDING_DESTINATION_APPROVAL, APPROVED, RESERVED, CANCELLED, REJECTED, EXPIRED
    status = Column(String(32), nullable=False, default="PROPOSED", index=True)
    priority = Column(String(32), nullable=False, default="MEDIUM") # CRITICAL, HIGH, MEDIUM, LOW
    expected_arrival_at = Column(DateTime(timezone=True), nullable=True)
    
    source_rationale = Column(JSON, nullable=False) # structured surplus evidence, safety stock buffer
    destination_rationale = Column(JSON, nullable=False) # structured need evidence, projected deficit
    optimisation_metadata = Column(JSON, nullable=True) # score, cost trade-off, rejected candidates
    
    proposal_version = Column(Integer, nullable=False, default=1)
    created_by_workflow_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    source_facility = relationship("Facility", foreign_keys=[source_facility_id])
    destination_facility = relationship("Facility", foreign_keys=[destination_facility_id])
    product = relationship("Product")
    batches = relationship("TransferProposalBatch", back_populates="proposal", cascade="all, delete-orphan")
    approvals = relationship("TransferApproval", back_populates="proposal", cascade="all, delete-orphan")
    transfer = relationship("Transfer", back_populates="proposal", uselist=False)

    __table_args__ = (
        Index("ix_proposals_status_priority", "status", "priority", "created_at"),
    )


class TransferProposalBatch(Base):
    __tablename__ = "transfer_proposal_batches"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    proposal_id = Column(String(36), ForeignKey("transfer_proposals.id"), nullable=False, index=True)
    batch_id = Column(String(36), ForeignKey("batches.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    unit = Column(String(32), nullable=False, default="UNIT")

    proposal = relationship("TransferProposal", back_populates="batches")
    batch = relationship("Batch")


class TransferApproval(Base):
    __tablename__ = "transfer_approvals"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    proposal_id = Column(String(36), ForeignKey("transfer_proposals.id"), nullable=False, index=True)
    proposal_version = Column(Integer, nullable=False)
    facility_id = Column(String(36), ForeignKey("facilities.id"), nullable=False, index=True)
    approver_user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    decision = Column(String(32), nullable=False) # APPROVED, REJECTED
    reason = Column(Text, nullable=True)
    decided_at = Column(DateTime(timezone=True), default=utc_now)

    proposal = relationship("TransferProposal", back_populates="approvals")
    approver = relationship("User")

    __table_args__ = (
        UniqueConstraint("proposal_id", "facility_id", "proposal_version", name="uq_proposal_facility_version"),
    )


from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, DateTime, ForeignKey, 
    Text, Boolean, JSON, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.organization import generate_uuid, utc_now


class Transfer(Base):
    """
    Physical stock transfer executing an approved and reserved TransferProposal.
    """
    __tablename__ = "transfers"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    proposal_id = Column(String(36), ForeignKey("transfer_proposals.id"), unique=True, nullable=False)
    status = Column(String(32), nullable=False, default="RESERVED", index=True)
    # RESERVED, READY_FOR_DISPATCH, DISPATCHED, IN_TRANSIT, RECEIVED, PARTIALLY_RECEIVED, RECONCILIATION_REQUIRED, REJECTED, CANCELLED, CLOSED
    source_facility_id = Column(String(36), ForeignKey("facilities.id"), nullable=False, index=True)
    destination_facility_id = Column(String(36), ForeignKey("facilities.id"), nullable=False, index=True)
    
    tracking_reference = Column(String(128), nullable=True) # External courier / vehicle reference
    created_at = Column(DateTime(timezone=True), default=utc_now)
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    proposal = relationship("TransferProposal", back_populates="transfer")
    source_facility = relationship("Facility", foreign_keys=[source_facility_id])
    destination_facility = relationship("Facility", foreign_keys=[destination_facility_id])
    packages = relationship("TransferPackage", back_populates="transfer", cascade="all, delete-orphan")
    scan_events = relationship("ScanEvent", back_populates="transfer", cascade="all, delete-orphan")


class TransferPackage(Base):
    __tablename__ = "transfer_packages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    transfer_id = Column(String(36), ForeignKey("transfers.id"), nullable=False, index=True)
    package_reference = Column(String(64), nullable=False) # e.g. "PKG-001"
    batch_id = Column(String(36), ForeignKey("batches.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    unit = Column(String(32), nullable=False, default="UNIT")
    status = Column(String(32), nullable=False, default="PREPARED") # PREPARED, DISPATCHED, RECEIVED, RECONCILED, DAMAGED

    transfer = relationship("Transfer", back_populates="packages")
    batch = relationship("Batch")
    label = relationship("SerializedLabel", back_populates="package", uselist=False, cascade="all, delete-orphan")


class SerializedLabel(Base):
    """
    Opaque serialized platform QR label.
    Stores only the SHA-256 hash of the random token to prevent tampering.
    """
    __tablename__ = "serialized_labels"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    transfer_package_id = Column(String(36), ForeignKey("transfer_packages.id"), unique=True, nullable=False)
    token_hash = Column(String(64), unique=True, nullable=False, index=True) # SHA-256 of token
    label_version = Column(Integer, nullable=False, default=1)
    status = Column(String(32), nullable=False, default="ISSUED") # ISSUED, DISPATCHED, RECEIVED, REVOKED
    issued_at = Column(DateTime(timezone=True), default=utc_now)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    package = relationship("TransferPackage", back_populates="label")
    scans = relationship("ScanEvent", back_populates="label")


class ScanEvent(Base):
    """
    Append-only audit record of every QR scan action.
    """
    __tablename__ = "scan_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    serialized_label_id = Column(String(36), ForeignKey("serialized_labels.id"), nullable=False, index=True)
    transfer_id = Column(String(36), ForeignKey("transfers.id"), nullable=False, index=True)
    facility_id = Column(String(36), ForeignKey("facilities.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    scan_type = Column(String(32), nullable=False) # DISPATCH, RECEIVE, VERIFY_ONLY
    result = Column(String(32), nullable=False) # SUCCESS, DUPLICATE_SCAN, WRONG_FACILITY, INVALID_STATE, REJECTED
    idempotency_key = Column(String(128), unique=True, nullable=True, index=True)
    device_reference = Column(String(128), nullable=True)
    scanned_at = Column(DateTime(timezone=True), default=utc_now)
    metadata_json = Column(JSON, nullable=True)

    label = relationship("SerializedLabel", back_populates="scans")
    transfer = relationship("Transfer", back_populates="scan_events")
    user = relationship("User")

    __table_args__ = (
        Index("ix_scan_transfer_time", "transfer_id", "scanned_at"),
    )


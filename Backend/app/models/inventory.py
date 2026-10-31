from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, DateTime, ForeignKey, 
    Text, Boolean, JSON, Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.organization import generate_uuid, utc_now


class FacilityBatchInventory(Base):
    """
    Materialized operational balance for a specific facility and batch.
    Usable eligible stock = on_hand_quantity - reserved_quantity - quarantined_quantity - damaged_quantity.
    """
    __tablename__ = "facility_batch_inventory"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    facility_id = Column(String(36), ForeignKey("facilities.id"), nullable=False, index=True)
    batch_id = Column(String(36), ForeignKey("batches.id"), nullable=False, index=True)
    on_hand_quantity = Column(Integer, nullable=False, default=0)
    reserved_quantity = Column(Integer, nullable=False, default=0)
    quarantined_quantity = Column(Integer, nullable=False, default=0)
    damaged_quantity = Column(Integer, nullable=False, default=0)
    unit = Column(String(32), nullable=False, default="UNIT")
    last_reconciled_at = Column(DateTime(timezone=True), default=utc_now)
    version = Column(Integer, nullable=False, default=1)  # Optimistic concurrency control

    facility = relationship("Facility", back_populates="inventories")
    batch = relationship("Batch", back_populates="inventories")

    @property
    def usable_quantity(self) -> int:
        return max(0, self.on_hand_quantity - self.reserved_quantity - self.quarantined_quantity - self.damaged_quantity)

    __table_args__ = (
        UniqueConstraint("facility_id", "batch_id", name="uq_facility_batch"),
        CheckConstraint("on_hand_quantity >= 0", name="chk_on_hand_non_negative"),
        CheckConstraint("reserved_quantity >= 0", name="chk_reserved_non_negative"),
        CheckConstraint("quarantined_quantity >= 0", name="chk_quarantined_non_negative"),
        CheckConstraint("damaged_quantity >= 0", name="chk_damaged_non_negative"),
        CheckConstraint("reserved_quantity <= on_hand_quantity", name="chk_reserved_le_on_hand"),
    )


class InventoryLedger(Base):
    """
    Auditable, immutable inventory movement ledger.
    Every consequential stock mutation records a compensating entry here.
    """
    __tablename__ = "inventory_ledger"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    facility_id = Column(String(36), ForeignKey("facilities.id"), nullable=False, index=True)
    batch_id = Column(String(36), ForeignKey("batches.id"), nullable=False, index=True)
    movement_type = Column(String(64), nullable=False) 
    # e.g., OPENING_BALANCE, PURCHASE_RECEIPT, CONSUMPTION, TRANSFER_RESERVATION, 
    # TRANSFER_DISPATCH, TRANSFER_RECEIPT, TRANSFER_REJECTION, DAMAGE, EXPIRY, ADJUSTMENT, RELEASE_FROM_QUARANTINE
    quantity_delta = Column(Integer, nullable=False) # Positive or negative
    unit = Column(String(32), nullable=False, default="UNIT")
    reference_type = Column(String(64), nullable=True) # TRANSFER, PURCHASE_ORDER, AUDIT, DISPATCH
    reference_id = Column(String(64), nullable=True, index=True)
    actor_id = Column(String(64), nullable=True)
    idempotency_key = Column(String(128), unique=True, nullable=True, index=True)
    occurred_at = Column(DateTime(timezone=True), default=utc_now)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    reason = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)

    batch = relationship("Batch", back_populates="ledger_entries")

    __table_args__ = (
        Index("ix_ledger_facility_batch_occurred", "facility_id", "batch_id", "occurred_at"),
    )


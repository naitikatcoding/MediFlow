from datetime import datetime, timezone, date
from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Date, ForeignKey, 
    Text, Boolean, JSON, Index, CheckConstraint
)
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.organization import generate_uuid, utc_now


class Product(Base):
    __tablename__ = "products"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    internal_code = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    generic_name = Column(String(255), nullable=False, index=True)
    brand_name = Column(String(255), nullable=True)
    strength = Column(String(64), nullable=False) # e.g. "500mg", "1g/vial"
    dosage_form = Column(String(64), nullable=False) # TABLET, INJECTION, VIAL, SYRUP, INFUSION
    pack_size = Column(Integer, nullable=False, default=1)
    base_unit = Column(String(32), nullable=False, default="UNIT") # TABLET, VIAL, AMPOULE, BOTTLE
    gtin = Column(String(64), nullable=True, index=True)
    storage_requirements = Column(String(128), nullable=False, default="ROOM_TEMPERATURE") # COLD_CHAIN_2_8C, ROOM_TEMPERATURE, CONTROLLED_SUBSTANCE
    transfer_policy_code = Column(String(64), nullable=False, default="STANDARD_ELIGIBLE") # STANDARD_ELIGIBLE, RESTRICTED_LOCAL_ONLY, CRITICAL_ESCALATION
    status = Column(String(32), nullable=False, default="ACTIVE")
    created_at = Column(DateTime(timezone=True), default=utc_now)

    batches = relationship("Batch", back_populates="product")
    consumptions = relationship("ConsumptionRecord", back_populates="product")


class Batch(Base):
    __tablename__ = "batches"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False, index=True)
    manufacturer_lot_number = Column(String(128), nullable=False, index=True)
    manufacturing_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=False, index=True)
    manufacturer = Column(String(255), nullable=False)
    supplier_id = Column(String(64), nullable=True)
    quality_status = Column(String(32), nullable=False, default="RELEASED") # RELEASED, QUARANTINED, RECALLED, DAMAGED
    created_at = Column(DateTime(timezone=True), default=utc_now)

    product = relationship("Product", back_populates="batches")
    inventories = relationship("FacilityBatchInventory", back_populates="batch")
    ledger_entries = relationship("InventoryLedger", back_populates="batch")

    __table_args__ = (
        Index("ix_batches_product_expiry", "product_id", "expiry_date"),
    )


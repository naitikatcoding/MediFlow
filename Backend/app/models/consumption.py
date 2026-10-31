from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, DateTime, ForeignKey, 
    Text, Boolean, JSON, Index, CheckConstraint
)
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.organization import generate_uuid, utc_now


class ConsumptionRecord(Base):
    __tablename__ = "consumption_records"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    facility_id = Column(String(36), ForeignKey("facilities.id"), nullable=False, index=True)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False, index=True)
    batch_id = Column(String(36), ForeignKey("batches.id"), nullable=True, index=True)
    quantity = Column(Integer, nullable=False)
    unit = Column(String(32), nullable=False, default="UNIT")
    consumed_at = Column(DateTime(timezone=True), nullable=False, index=True)
    source_system = Column(String(64), nullable=False, default="SYNTHETIC_HIS")
    import_job_id = Column(String(36), nullable=True)
    data_quality_status = Column(String(32), nullable=False, default="VALIDATED") # VALIDATED, SUSPECT, INTERPOLATED
    created_at = Column(DateTime(timezone=True), default=utc_now)

    product = relationship("Product", back_populates="consumptions")

    __table_args__ = (
        Index("ix_consumption_fac_prod_date", "facility_id", "product_id", "consumed_at"),
        CheckConstraint("quantity >= 0", name="chk_consumption_quantity_non_negative"),
    )


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    facility_id = Column(String(36), ForeignKey("facilities.id"), nullable=False, index=True)
    supplier_id = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="PLACED") # PLACED, CONFIRMED, IN_TRANSIT, RECEIVED, CANCELLED
    expected_delivery_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    lines = relationship("PurchaseOrderLine", back_populates="purchase_order")


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    purchase_order_id = Column(String(36), ForeignKey("purchase_orders.id"), nullable=False)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False)
    quantity_ordered = Column(Integer, nullable=False)
    quantity_received = Column(Integer, nullable=False, default=0)
    unit = Column(String(32), nullable=False, default="UNIT")

    purchase_order = relationship("PurchaseOrder", back_populates="lines")


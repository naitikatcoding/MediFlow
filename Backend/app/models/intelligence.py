from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, DateTime, ForeignKey, 
    Text, Boolean, JSON, Index
)
from app.core.database import Base
from app.models.organization import generate_uuid, utc_now


class ForecastRun(Base):
    __tablename__ = "forecast_runs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    facility_id = Column(String(36), ForeignKey("facilities.id"), nullable=False, index=True)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False, index=True)
    model_name = Column(String(64), nullable=False, default="WEIGHTED_MOVING_AVERAGE")
    horizon_start = Column(DateTime(timezone=True), nullable=False)
    horizon_end = Column(DateTime(timezone=True), nullable=False)
    forecast_payload = Column(JSON, nullable=False) # e.g. {"daily_estimates": [...], "projected_demand": 120, "history_days": 60}
    metrics = Column(JSON, nullable=True) # e.g. {"confidence_score": 0.88, "cv": 0.22, "trend_direction": "UP"}
    data_quality_score = Column(Float, nullable=False, default=1.0) # 0.0 to 1.0
    created_at = Column(DateTime(timezone=True), default=utc_now)


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    facility_id = Column(String(36), ForeignKey("facilities.id"), nullable=False, index=True)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False, index=True)
    risk_type = Column(String(32), nullable=False) # STOCKOUT_RISK, EXPIRY_RISK, SURPLUS_AVAILABLE
    risk_level = Column(String(32), nullable=False) # CRITICAL, HIGH, MEDIUM, LOW, SAFE
    score = Column(Float, nullable=False) # 0.0 to 100.0
    explanation = Column(JSON, nullable=False) # structured breakdown, days_of_cover, surplus_qty, etc.
    forecast_run_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (
        Index("ix_risk_fac_type_level", "facility_id", "risk_type", "risk_level"),
    )


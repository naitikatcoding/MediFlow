import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, DateTime, ForeignKey, 
    Text, Boolean, Enum, JSON, UniqueConstraint, Index, CheckConstraint
)
from sqlalchemy.orm import relationship
from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Organisation(Base):
    __tablename__ = "organisations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    organisation_type = Column(String(64), nullable=False, default="HEALTHCARE_NETWORK")
    status = Column(String(32), nullable=False, default="ACTIVE")
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    facilities = relationship("Facility", back_populates="organisation")
    users = relationship("User", back_populates="organisation")


class Facility(Base):
    __tablename__ = "facilities"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organisation_id = Column(String(36), ForeignKey("organisations.id"), nullable=False)
    name = Column(String(255), nullable=False)
    facility_type = Column(String(64), nullable=False)  # HOSPITAL, DIAGNOSTIC_CENTRE, PHARMACY
    address = Column(String(500), nullable=True)
    city = Column(String(100), nullable=True)
    timezone = Column(String(64), nullable=False, default="Asia/Kolkata")
    status = Column(String(32), nullable=False, default="ACTIVE")
    storage_capabilities = Column(JSON, nullable=True)  # {"cold_chain": true, "ambient_max_c": 25, "narcotics_vault": false}
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    organisation = relationship("Organisation", back_populates="facilities")
    memberships = relationship("FacilityMembership", back_populates="facility")
    inventories = relationship("FacilityBatchInventory", back_populates="facility")


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organisation_id = Column(String(36), ForeignKey("organisations.id"), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    role = Column(String(64), nullable=False, default="PHARMACIST") # PHARMACIST, MEDICAL_SUPERINTENDENT, NETWORK_ADMIN
    status = Column(String(32), nullable=False, default="ACTIVE")
    created_at = Column(DateTime(timezone=True), default=utc_now)

    organisation = relationship("Organisation", back_populates="users")
    memberships = relationship("FacilityMembership", back_populates="user")


class FacilityMembership(Base):
    __tablename__ = "facility_memberships"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    facility_id = Column(String(36), ForeignKey("facilities.id"), nullable=False)
    role = Column(String(64), nullable=False) # PHARMACIST, APPROVER, DISPATCHER, RECEIVER
    status = Column(String(32), nullable=False, default="ACTIVE")
    created_at = Column(DateTime(timezone=True), default=utc_now)

    user = relationship("User", back_populates="memberships")
    facility = relationship("Facility", back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("user_id", "facility_id", "role", name="uq_user_facility_role"),
    )


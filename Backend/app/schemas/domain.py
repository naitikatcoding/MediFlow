from typing import List, Optional, Dict, Any
from datetime import datetime, date
from pydantic import BaseModel, Field, ConfigDict


# Base schemas
class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# Facility
class StorageCapabilities(BaseModel):
    cold_chain: bool = False
    ambient_max_c: int = 25
    narcotics_vault: bool = False
    cleanroom: bool = False


class FacilityResponse(BaseSchema):
    id: str
    organisation_id: str
    name: str
    facility_type: str
    address: Optional[str] = None
    city: Optional[str] = None
    timezone: str
    status: str
    storage_capabilities: Optional[Dict[str, Any]] = None


# Product & Batch
class ProductResponse(BaseSchema):
    id: str
    internal_code: str
    name: str
    generic_name: str
    brand_name: Optional[str] = None
    strength: str
    dosage_form: str
    pack_size: int
    base_unit: str
    gtin: Optional[str] = None
    storage_requirements: str
    transfer_policy_code: str
    status: str


class BatchResponse(BaseSchema):
    id: str
    product_id: str
    manufacturer_lot_number: str
    manufacturing_date: Optional[date] = None
    expiry_date: date
    manufacturer: str
    quality_status: str
    days_to_expiry: Optional[int] = None


# Inventory & Ledger
class InventoryItemResponse(BaseSchema):
    id: str
    facility_id: str
    facility_name: Optional[str] = None
    batch_id: str
    product_id: str
    product_name: str
    generic_name: str
    strength: str
    dosage_form: str
    storage_requirements: str
    manufacturer_lot_number: str
    expiry_date: date
    days_to_expiry: int
    on_hand_quantity: int
    reserved_quantity: int
    quarantined_quantity: int
    damaged_quantity: int
    usable_quantity: int
    unit: str
    last_reconciled_at: Optional[datetime] = None


class LedgerEntryResponse(BaseSchema):
    id: str
    facility_id: str
    batch_id: str
    movement_type: str
    quantity_delta: int
    unit: str
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    actor_id: Optional[str] = None
    occurred_at: datetime
    reason: Optional[str] = None


# Forecast & Risk
class ForecastDayEstimate(BaseModel):
    date: str
    estimated_demand: float
    confidence_lower: float
    confidence_upper: float


class ForecastResponse(BaseSchema):
    id: str
    facility_id: str
    product_id: str
    model_name: str
    horizon_days: int
    projected_total_demand: float
    daily_average_demand: float
    confidence_score: float
    data_quality_score: float
    warnings: List[str] = []
    daily_estimates: List[ForecastDayEstimate] = []


class RiskAssessmentResponse(BaseSchema):
    id: str
    facility_id: str
    facility_name: Optional[str] = None
    product_id: str
    product_name: Optional[str] = None
    risk_type: str  # STOCKOUT_RISK, EXPIRY_RISK, SURPLUS_AVAILABLE
    risk_level: str # CRITICAL, HIGH, MEDIUM, LOW, SAFE
    score: float
    days_of_cover: Optional[float] = None
    projected_stockout_date: Optional[str] = None
    at_risk_quantity: Optional[int] = None
    explanation: Dict[str, Any]
    created_at: datetime


# Matching & Proposal
class ProposalBatchItem(BaseModel):
    batch_id: str
    manufacturer_lot_number: str
    expiry_date: date
    quantity: int
    unit: str


class TransferProposalResponse(BaseSchema):
    id: str
    source_facility_id: str
    source_facility_name: Optional[str] = None
    destination_facility_id: str
    destination_facility_name: Optional[str] = None
    product_id: str
    product_name: Optional[str] = None
    proposed_quantity: int
    unit: str
    status: str
    priority: str
    expected_arrival_at: Optional[datetime] = None
    source_rationale: Dict[str, Any]
    destination_rationale: Dict[str, Any]
    optimisation_metadata: Optional[Dict[str, Any]] = None
    proposal_version: int
    batches: List[ProposalBatchItem] = []
    source_approved: bool = False
    destination_approved: bool = False
    can_reserve: bool = False
    created_at: datetime


class ProposalApprovalRequest(BaseModel):
    proposal_version: int
    facility_id: str
    approver_user_id: str
    decision: str = "APPROVED"  # APPROVED or REJECTED
    reason: Optional[str] = "Approved after clinical inventory review"


# Transfer, Packages & QR
class SerializedLabelResponse(BaseSchema):
    id: str
    transfer_package_id: str
    label_version: int
    status: str
    token_preview: str # masked token prefix
    qr_code_data_uri: Optional[str] = None
    issued_at: datetime


class TransferPackageResponse(BaseSchema):
    id: str
    transfer_id: str
    package_reference: str
    batch_id: str
    manufacturer_lot_number: Optional[str] = None
    expiry_date: Optional[date] = None
    quantity: int
    unit: str
    status: str
    label: Optional[SerializedLabelResponse] = None


class TransferResponse(BaseSchema):
    id: str
    proposal_id: str
    status: str
    source_facility_id: str
    source_facility_name: Optional[str] = None
    destination_facility_id: str
    destination_facility_name: Optional[str] = None
    product_name: Optional[str] = None
    quantity: int = 0
    unit: str = "UNIT"
    tracking_reference: Optional[str] = None
    created_at: datetime
    dispatched_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    packages: List[TransferPackageResponse] = []


class ScanRequest(BaseModel):
    token: str
    facility_id: str
    user_id: str
    scan_type: str # DISPATCH or RECEIVE
    idempotency_key: str
    accepted_quantity: Optional[int] = None
    damaged_quantity: Optional[int] = 0
    notes: Optional[str] = None


class ScanResultResponse(BaseModel):
    success: bool
    scan_type: str
    status: str
    message: str
    transfer_id: Optional[str] = None
    package_id: Optional[str] = None
    product_name: Optional[str] = None
    lot_number: Optional[str] = None
    expiry_date: Optional[str] = None
    verified_quantity: Optional[int] = None
    ledger_updated: bool = False
    timestamp: datetime


# Dashboard Overview
class DashboardOverviewResponse(BaseModel):
    total_facilities: int
    monitored_products: int
    active_stockout_risks: int
    critical_stockout_risks: int
    active_expiry_risks: int
    transferable_surplus_units: int
    active_proposals: int
    in_transit_transfers: int
    completed_redistributions: int
    simulated_wastage_prevented_units: int
    system_mode: str = "SIMULATION"
    integrations: Dict[str, str] = {
        "gemini": "CONNECTED",
        "meko": "LOCAL_TRACE_ADAPTER",
        "database": "OPERATIONAL_TRUTH"
    }


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
class ProductCreate(BaseModel):
    internal_code: str
    name: str
    generic_name: str
    brand_name: Optional[str] = None
    strength: str
    dosage_form: str
    pack_size: int = 1
    base_unit: str = "UNIT"
    gtin: Optional[str] = None
    storage_requirements: str = "ROOM_TEMPERATURE"
    transfer_policy_code: str = "STANDARD_ELIGIBLE"
    status: str = "ACTIVE"


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


class BatchCreate(BaseModel):
    product_id: str
    manufacturer_lot_number: str
    manufacturing_date: Optional[date] = None
    expiry_date: date
    manufacturer: str
    supplier_id: Optional[str] = None
    quality_status: str = "RELEASED"


class BatchResponse(BaseSchema):
    id: str
    product_id: str
    manufacturer_lot_number: str
    manufacturing_date: Optional[date] = None
    expiry_date: date
    manufacturer: str
    quality_status: str
    days_to_expiry: Optional[int] = None


class BatchDetailResponse(BaseSchema):
    id: str
    product_id: str
    product_name: str
    product_code: str
    generic_name: str
    strength: str
    dosage_form: str
    storage_requirements: str
    manufacturer_lot_number: str
    manufacturing_date: Optional[date] = None
    expiry_date: date
    days_to_expiry: int
    manufacturer: str
    supplier_id: Optional[str] = None
    quality_status: str
    is_blocked: bool
    blocking_reasons: List[str] = []
    facilities_stock: List[Dict[str, Any]] = []


class BatchEligibilityCheck(BaseModel):
    batch_id: str
    is_eligible: bool
    is_blocked: bool
    blocking_reasons: List[str] = []
    days_to_expiry: int
    remaining_shelf_life_days: int
    storage_compatible: bool


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
    quality_status: Optional[str] = "RELEASED"
    is_blocked: Optional[bool] = False
    data_freshness_status: Optional[str] = "FRESH"
    last_reconciled_at: Optional[datetime] = None


class InventorySummaryResponse(BaseModel):
    facility_id: Optional[str] = None
    total_on_hand: int
    total_reserved: int
    total_quarantined: int
    total_damaged: int
    total_usable: int
    distinct_products_count: int
    distinct_batches_count: int
    near_expiry_batches_count: int
    cold_chain_items_count: int
    data_freshness_status: str = "FRESH"
    last_updated_at: Optional[datetime] = None


class FacilityProductDetailResponse(BaseModel):
    facility_id: str
    facility_name: str
    product_id: str
    product_name: str
    generic_name: str
    strength: str
    dosage_form: str
    base_unit: str
    storage_requirements: str
    total_on_hand: int
    total_reserved: int
    total_quarantined: int
    total_damaged: int
    total_usable: int
    data_freshness_status: str
    batches: List[InventoryItemResponse]


class InventoryAdjustmentRequest(BaseModel):
    facility_id: str
    batch_id: str
    adjustment_type: str = Field(..., description="ADJUSTMENT, DAMAGE, QUARANTINE, RELEASE_FROM_QUARANTINE, RETURN, EXPIRY")
    quantity_delta: int = Field(..., description="Quantity change (+ for addition/release, - for deduction/quarantine)")
    unit: str = "UNIT"
    reason: str = Field(..., min_length=3, description="Mandatory audit explanation for the adjustment")
    actor_id: str = Field(..., min_length=1, description="Authorized user or system identity performing adjustment")
    reference_id: Optional[str] = None
    idempotency_key: Optional[str] = None


class InventoryAdjustmentResponse(BaseModel):
    success: bool
    ledger_id: str
    movement_type: str
    quantity_delta: int
    updated_on_hand: int
    updated_usable: int
    updated_reserved: int
    updated_quarantined: int
    updated_damaged: int
    occurred_at: datetime
    audit_id: Optional[str] = None
    message: str


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
    idempotency_key: Optional[str] = None
    occurred_at: datetime
    reason: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None


# Import Jobs
class ImportJobResponse(BaseSchema):
    id: str
    facility_id: str
    source_type: str
    filename: Optional[str] = None
    status: str
    row_count: int
    accepted_count: int
    rejected_count: int
    error_summary: Optional[Dict[str, Any]] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class ImportJobErrorDetail(BaseModel):
    job_id: str
    facility_id: str
    status: str
    row_count: int
    accepted_count: int
    rejected_count: int
    errors: List[Dict[str, Any]]


# Reconciliation
class ReconciliationResult(BaseModel):
    facility_id: str
    batch_id: str
    product_name: Optional[str] = None
    lot_number: Optional[str] = None
    materialized_on_hand: int
    ledger_computed_on_hand: int
    discrepancy: int
    is_balanced: bool
    last_reconciled_at: datetime


class FacilityReconciliationResponse(BaseModel):
    facility_id: str
    reconciled_batches_count: int
    balanced_batches_count: int
    discrepancy_count: int
    results: List[ReconciliationResult]


# FEFO Allocation
class FefoAllocationItem(BaseModel):
    batch_id: str
    manufacturer_lot_number: str
    expiry_date: date
    days_to_expiry: int
    allocated_quantity: int
    unit: str


class FefoAllocationRequest(BaseModel):
    facility_id: str
    product_id: str
    requested_quantity: int
    destination_facility_id: Optional[str] = None
    min_shelf_life_days: int = 15


class FefoAllocationResponse(BaseModel):
    facility_id: str
    product_id: str
    requested_quantity: int
    allocated_total: int
    unallocated_deficit: int
    is_fully_allocated: bool
    allocations: List[FefoAllocationItem]


# Forecast & Risk
class ForecastDayEstimate(BaseModel):
    date: str
    estimated_demand: float
    confidence_lower: float
    confidence_upper: float


class ForecastTrajectoryItem(BaseModel):
    day: int
    date: str
    starting_stock: int
    demand: float
    inbound: int
    ending_stock: int
    below_safety_stock: bool = False
    is_stockout: bool = False


class ForecastRunRequest(BaseModel):
    facility_id: Optional[str] = None
    product_id: Optional[str] = None
    horizon_days: int = 30


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
    demand_7d: Optional[float] = None
    demand_30d: Optional[float] = None
    unit: Optional[str] = "UNIT"
    warnings: List[str] = []
    daily_estimates: List[ForecastDayEstimate] = []
    projected_stock_trajectory: Optional[List[ForecastTrajectoryItem]] = None
    summary: Optional[Dict[str, Any]] = None


class ForecastRunItem(BaseModel):
    forecast_id: str
    facility_id: str
    product_id: str
    daily_average_demand: float
    projected_total_demand: float
    confidence_score: float
    warnings_count: int


class ForecastRunBatchResponse(BaseModel):
    total_runs: int
    runs: List[ForecastRunItem]


class RiskSummaryCount(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    safe: int = 0
    total: int = 0


class RisksSummaryResponse(BaseModel):
    total_risks: int
    stockout_risks: RiskSummaryCount
    expiry_risks: RiskSummaryCount
    surplus_available: int
    critical_alerts: int
    by_facility: Dict[str, Dict[str, int]] = {}


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


class ProposalGenerateRequest(BaseModel):
    product_id: Optional[str] = None
    facility_id: Optional[str] = None
    auto_create_top: Optional[int] = 0
    min_score: float = 40.0


class ProposalGenerateResponse(BaseModel):
    total_candidates_evaluated: int
    accepted_count: int
    rejected_count: int
    proposals_created: List[Dict[str, Any]] = []
    accepted_opportunities: List[Dict[str, Any]] = []
    rejected_candidates: List[Dict[str, Any]] = []


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


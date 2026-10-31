from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models.inventory import InventoryLedger
from app.services.inventory_service import InventoryService
from app.services.ledger_service import LedgerService
from app.schemas.domain import (
    InventoryItemResponse,
    LedgerEntryResponse,
    InventorySummaryResponse,
    FacilityProductDetailResponse,
    InventoryAdjustmentRequest,
    InventoryAdjustmentResponse,
    FefoAllocationRequest,
    FefoAllocationResponse,
    ReconciliationResult,
    FacilityReconciliationResponse
)

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("", response_model=List[InventoryItemResponse])
def get_inventory(
    facility_id: Optional[str] = None,
    product_id: Optional[str] = None,
    storage: Optional[str] = None,
    near_expiry_days: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Facility-scoped inventory list with lot-level status and FEFO ordering."""
    return InventoryService.get_facility_inventory(
        db,
        facility_id=facility_id,
        product_id=product_id,
        storage=storage,
        near_expiry_days=near_expiry_days
    )


@router.get("/summary", response_model=InventorySummaryResponse)
def get_inventory_summary(
    facility_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Network-wide or facility-specific inventory aggregated summary."""
    return InventoryService.get_inventory_summary(db, facility_id=facility_id)


@router.get("/ledger", response_model=List[LedgerEntryResponse])
def get_ledger(
    facility_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    movement_type: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Auditable, immutable inventory movement ledger events."""
    query = db.query(InventoryLedger)
    if facility_id:
        query = query.filter(InventoryLedger.facility_id == facility_id)
    if batch_id:
        query = query.filter(InventoryLedger.batch_id == batch_id)
    if movement_type:
        query = query.filter(InventoryLedger.movement_type == movement_type)

    return query.order_by(InventoryLedger.occurred_at.desc()).offset(offset).limit(limit).all()


@router.get("/ledger/{entry_id}", response_model=LedgerEntryResponse)
def get_ledger_entry(entry_id: str, db: Session = Depends(get_db)):
    """Retrieve specific ledger movement record."""
    entry = db.query(InventoryLedger).filter(InventoryLedger.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Ledger entry not found")
    return entry


@router.post("/adjustments", response_model=InventoryAdjustmentResponse)
def record_inventory_adjustment(
    payload: InventoryAdjustmentRequest,
    db: Session = Depends(get_db)
):
    """
    Authorised inventory adjustment workflow.
    Validates reason, actor, invariants against negative stock, and writes to immutable ledger.
    """
    try:
        entry = LedgerService.record_movement(
            db=db,
            facility_id=payload.facility_id,
            batch_id=payload.batch_id,
            movement_type=payload.adjustment_type,
            quantity_delta=payload.quantity_delta,
            unit=payload.unit,
            reference_type="MANUAL_ADJUSTMENT",
            reference_id=payload.reference_id,
            actor_id=payload.actor_id,
            idempotency_key=payload.idempotency_key,
            reason=payload.reason
        )
        db.commit()

        # Fetch updated balances
        from app.models.inventory import FacilityBatchInventory
        inv = db.query(FacilityBatchInventory).filter(
            FacilityBatchInventory.facility_id == payload.facility_id,
            FacilityBatchInventory.batch_id == payload.batch_id
        ).first()

        return InventoryAdjustmentResponse(
            success=True,
            ledger_id=entry.id,
            movement_type=entry.movement_type,
            quantity_delta=entry.quantity_delta,
            updated_on_hand=inv.on_hand_quantity if inv else 0,
            updated_usable=inv.usable_quantity if inv else 0,
            updated_reserved=inv.reserved_quantity if inv else 0,
            updated_quarantined=inv.quarantined_quantity if inv else 0,
            updated_damaged=inv.damaged_quantity if inv else 0,
            occurred_at=entry.occurred_at,
            message="Inventory adjustment recorded successfully."
        )
    except ValueError as ve:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/fefo-allocate", response_model=FefoAllocationResponse)
def allocate_batches_fefo(
    payload: FefoAllocationRequest,
    db: Session = Depends(get_db)
):
    """FEFO-aware batch allocation helper for proposals, orders, or dispensing."""
    return InventoryService.allocate_fefo(
        db=db,
        facility_id=payload.facility_id,
        product_id=payload.product_id,
        requested_quantity=payload.requested_quantity,
        destination_facility_id=payload.destination_facility_id,
        min_shelf_life_days=payload.min_shelf_life_days
    )


@router.post("/reconcile/{facility_id}/{batch_id}", response_model=ReconciliationResult)
def reconcile_batch(
    facility_id: str,
    batch_id: str,
    db: Session = Depends(get_db)
):
    """Reconcile materialised inventory with sum of immutable ledger entries for a batch."""
    return InventoryService.reconcile_batch_with_ledger(db, facility_id, batch_id)


@router.get("/reconciliation/{facility_id}", response_model=FacilityReconciliationResponse)
def get_facility_reconciliation(
    facility_id: str,
    db: Session = Depends(get_db)
):
    """Audit materialised vs ledger balance integrity across all batches at a facility."""
    return InventoryService.reconcile_facility(db, facility_id)


@router.get("/{facility_id}/{product_id}", response_model=FacilityProductDetailResponse)
def get_facility_product_inventory(
    facility_id: str,
    product_id: str,
    db: Session = Depends(get_db)
):
    """Batch breakdown and data freshness for a specific product at a facility."""
    detail = InventoryService.get_facility_product_detail(db, facility_id, product_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Product or facility inventory record not found.")
    return detail

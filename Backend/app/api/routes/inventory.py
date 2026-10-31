from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models.inventory import InventoryLedger
from app.services.inventory_service import InventoryService
from app.schemas.domain import InventoryItemResponse, LedgerEntryResponse

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("", response_model=List[InventoryItemResponse])
def get_inventory(
    facility_id: Optional[str] = None,
    product_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    return InventoryService.get_facility_inventory(db, facility_id=facility_id, product_id=product_id)


@router.get("/ledger", response_model=List[LedgerEntryResponse])
def get_ledger(
    facility_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    query = db.query(InventoryLedger)
    if facility_id:
        query = query.filter(InventoryLedger.facility_id == facility_id)
    if batch_id:
        query = query.filter(InventoryLedger.batch_id == batch_id)
    return query.order_by(InventoryLedger.occurred_at.desc()).limit(limit).all()


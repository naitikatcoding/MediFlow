import uuid
from typing import List, Optional
from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models.product import Product, Batch
from app.models.inventory import FacilityBatchInventory
from app.models.organization import Facility
from app.services.inventory_service import InventoryService
from app.schemas.domain import (
    ProductResponse,
    ProductCreate,
    BatchResponse,
    BatchCreate,
    BatchDetailResponse,
    BatchEligibilityCheck
)

router = APIRouter(tags=["products"])


@router.get("/products", response_model=List[ProductResponse])
def list_products(
    storage: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Retrieve full product catalogue with optional search and storage condition filter."""
    query = db.query(Product)
    if storage:
        query = query.filter(Product.storage_requirements == storage)
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(
            (Product.name.ilike(s)) |
            (Product.generic_name.ilike(s)) |
            (Product.internal_code.ilike(s))
        )
    return query.order_by(Product.name.asc()).all()


@router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    """Add a new medicine product to the network catalogue."""
    existing = db.query(Product).filter(Product.internal_code == payload.internal_code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Product with code '{payload.internal_code}' already exists.")

    prod = Product(
        id=str(uuid.uuid4()),
        internal_code=payload.internal_code,
        name=payload.name,
        generic_name=payload.generic_name,
        brand_name=payload.brand_name,
        strength=payload.strength,
        dosage_form=payload.dosage_form,
        pack_size=payload.pack_size,
        base_unit=payload.base_unit,
        gtin=payload.gtin,
        storage_requirements=payload.storage_requirements,
        transfer_policy_code=payload.transfer_policy_code,
        status=payload.status,
        created_at=datetime.now(timezone.utc)
    )
    db.add(prod)
    db.commit()
    db.refresh(prod)
    return prod


@router.get("/products/{product_id}", response_model=ProductResponse)
def get_product(product_id: str, db: Session = Depends(get_db)):
    """Fetch product details by ID."""
    prod = db.query(Product).filter(Product.id == product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
    return prod


@router.get("/products/{product_id}/batches", response_model=List[BatchResponse])
def list_product_batches(product_id: str, db: Session = Depends(get_db)):
    """List all manufactured batches for a product sorted in FEFO order."""
    prod = db.query(Product).filter(Product.id == product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")

    batches = db.query(Batch).filter(Batch.product_id == product_id).order_by(Batch.expiry_date.asc()).all()
    today = date.today()
    result = []
    for b in batches:
        days = (b.expiry_date - today).days
        result.append(BatchResponse(
            id=b.id,
            product_id=b.product_id,
            manufacturer_lot_number=b.manufacturer_lot_number,
            manufacturing_date=b.manufacturing_date,
            expiry_date=b.expiry_date,
            manufacturer=b.manufacturer,
            quality_status=b.quality_status,
            days_to_expiry=days
        ))
    return result


@router.post("/batches", response_model=BatchResponse, status_code=status.HTTP_201_CREATED)
def create_batch(payload: BatchCreate, db: Session = Depends(get_db)):
    """Register a new manufactured batch lot for a product."""
    prod = db.query(Product).filter(Product.id == payload.product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Referenced product not found in catalogue.")

    existing = db.query(Batch).filter(
        Batch.product_id == payload.product_id,
        Batch.manufacturer_lot_number == payload.manufacturer_lot_number
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Batch lot '{payload.manufacturer_lot_number}' already exists for this product.")

    batch = Batch(
        id=str(uuid.uuid4()),
        product_id=payload.product_id,
        manufacturer_lot_number=payload.manufacturer_lot_number,
        manufacturing_date=payload.manufacturing_date,
        expiry_date=payload.expiry_date,
        manufacturer=payload.manufacturer,
        supplier_id=payload.supplier_id,
        quality_status=payload.quality_status,
        created_at=datetime.now(timezone.utc)
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    today = date.today()
    return BatchResponse(
        id=batch.id,
        product_id=batch.product_id,
        manufacturer_lot_number=batch.manufacturer_lot_number,
        manufacturing_date=batch.manufacturing_date,
        expiry_date=batch.expiry_date,
        manufacturer=batch.manufacturer,
        quality_status=batch.quality_status,
        days_to_expiry=(batch.expiry_date - today).days
    )


@router.get("/batches/{batch_id}", response_model=BatchDetailResponse)
def get_batch_detail(batch_id: str, db: Session = Depends(get_db)):
    """Detailed batch lot information, blocking status, and facility stock balances."""
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    product = db.query(Product).filter(Product.id == batch.product_id).first()
    today = date.today()
    days_to_expiry = (batch.expiry_date - today).days

    eligibility = InventoryService.check_batch_eligibility(db, batch.id)

    # Fetch facility allocations
    inventories = db.query(FacilityBatchInventory, Facility).join(
        Facility, FacilityBatchInventory.facility_id == Facility.id
    ).filter(
        FacilityBatchInventory.batch_id == batch_id
    ).all()

    facilities_stock = []
    for inv, fac in inventories:
        facilities_stock.append({
            "facility_id": fac.id,
            "facility_name": fac.name,
            "on_hand": inv.on_hand_quantity,
            "reserved": inv.reserved_quantity,
            "quarantined": inv.quarantined_quantity,
            "damaged": inv.damaged_quantity,
            "usable": inv.usable_quantity,
            "unit": inv.unit,
            "last_reconciled_at": inv.last_reconciled_at
        })

    return BatchDetailResponse(
        id=batch.id,
        product_id=product.id if product else batch.product_id,
        product_name=product.name if product else "Unknown",
        product_code=product.internal_code if product else "UNKNOWN",
        generic_name=product.generic_name if product else "Unknown",
        strength=product.strength if product else "",
        dosage_form=product.dosage_form if product else "",
        storage_requirements=product.storage_requirements if product else "ROOM_TEMPERATURE",
        manufacturer_lot_number=batch.manufacturer_lot_number,
        manufacturing_date=batch.manufacturing_date,
        expiry_date=batch.expiry_date,
        days_to_expiry=days_to_expiry,
        manufacturer=batch.manufacturer,
        supplier_id=batch.supplier_id,
        quality_status=batch.quality_status,
        is_blocked=eligibility["is_blocked"],
        blocking_reasons=eligibility["blocking_reasons"],
        facilities_stock=facilities_stock
    )


@router.get("/batches/{batch_id}/eligibility", response_model=BatchEligibilityCheck)
def check_batch_transfer_eligibility(
    batch_id: str,
    destination_facility_id: Optional[str] = None,
    min_shelf_life_days: int = Query(15, ge=1),
    db: Session = Depends(get_db)
):
    """Inspect whether a specific batch lot is eligible or blocked for redistribution."""
    return InventoryService.check_batch_eligibility(
        db=db,
        batch_id=batch_id,
        destination_facility_id=destination_facility_id,
        min_shelf_life_days=min_shelf_life_days
    )

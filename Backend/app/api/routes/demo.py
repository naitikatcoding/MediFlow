from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.services.seed_service import seed_database
from app.models.inventory import FacilityBatchInventory
from app.models.product import Product, Batch
from app.models.organization import Facility, User

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/reset")
def reset_and_seed_demo_data(db: Session = Depends(get_db)):
    """
    Deterministic seed command: Drops tables, runs schema migrations,
    and seeds 4 facilities, 16 medicines, 10 weeks of consumption history,
    active proposals, and pre-issued QR packages.
    """
    try:
        result = seed_database(db=db, force_reset=True)
        return {
            "success": True,
            "message": "Database reset and seeded successfully with synthetic healthcare data.",
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database reset error: {str(e)}")


@router.post("/simulate-stock-change")
def simulate_stock_change_edge_case(
    product_code: str = "MED-003", # Ceftriaxone
    facility_key: str = "apex",
    new_usable_quantity: int = 5,
    db: Session = Depends(get_db)
):
    """
    Simulates a sudden emergency consumption event at the source facility before reservation.
    When the reservation transaction attempts to execute, it detects insufficient stock,
    safely aborts without committing an invalid transfer, and triggers automatic re-planning!
    """
    prod = db.query(Product).filter(Product.internal_code == product_code).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")

    batch = db.query(Batch).filter(Batch.product_id == prod.id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    fac = db.query(Facility).filter(Facility.name.ilike(f"%{facility_key}%")).first()
    if not fac:
        raise HTTPException(status_code=404, detail="Facility not found")

    inv = db.query(FacilityBatchInventory).filter(
        FacilityBatchInventory.facility_id == fac.id,
        FacilityBatchInventory.batch_id == batch.id
    ).first()

    if inv:
        inv.on_hand_quantity = new_usable_quantity
        inv.reserved_quantity = 0
        db.commit()
        return {
            "success": True,
            "message": f"Simulated stock shock: On-hand quantity for {prod.name} at {fac.name} reduced to {new_usable_quantity} units. Now attempts to reserve larger amounts will trigger safe failure and re-planning."
        }

    return {"success": False, "message": "Inventory record not found"}


@router.get("/context")
def get_demo_context(db: Session = Depends(get_db)):
    """Provides UI with quick switchable users, facilities, and scannable test tokens."""
    facilities = db.query(Facility).all()
    users = db.query(User).all()

    return {
        "facilities": [{"id": f.id, "name": f.name, "type": f.facility_type, "capabilities": f.storage_capabilities} for f in facilities],
        "users": [{"id": u.id, "name": u.name, "email": u.email, "role": u.role} for u in users],
        "demo_qr_token": "SOS_DEMO_TRANSFER_TOKEN_VALID_2026"
    }


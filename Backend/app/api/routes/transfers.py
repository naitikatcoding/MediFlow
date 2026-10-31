from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models.transfer import Transfer, TransferPackage, SerializedLabel
from app.models.proposal import TransferProposal
from app.models.product import Product, Batch
from app.models.organization import Facility
from app.schemas.domain import TransferResponse, TransferPackageResponse, SerializedLabelResponse
from app.services.qr_service import QRService

router = APIRouter(prefix="/transfers", tags=["transfers"])


@router.get("", response_model=List[TransferResponse])
def list_transfers(
    status: Optional[str] = None,
    facility_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Transfer)
    if status:
        query = query.filter(Transfer.status == status)
    if facility_id:
        query = query.filter(
            (Transfer.source_facility_id == facility_id) |
            (Transfer.destination_facility_id == facility_id)
        )
    transfers = query.order_by(Transfer.created_at.desc()).all()

    results = []
    for t in transfers:
        src = db.query(Facility).filter(Facility.id == t.source_facility_id).first()
        dest = db.query(Facility).filter(Facility.id == t.destination_facility_id).first()
        prop = db.query(TransferProposal).filter(TransferProposal.id == t.proposal_id).first()
        prod = db.query(Product).filter(Product.id == prop.product_id).first() if prop else None

        packages_data = []
        total_qty = 0
        for pkg in t.packages:
            batch = db.query(Batch).filter(Batch.id == pkg.batch_id).first()
            label_data = None
            if pkg.label:
                label_data = {
                    "id": pkg.label.id,
                    "transfer_package_id": pkg.label.transfer_package_id,
                    "label_version": pkg.label.label_version,
                    "status": pkg.label.status,
                    "token_preview": f"HASH_{pkg.label.token_hash[:8]}...",
                    "qr_code_data_uri": None,
                    "issued_at": pkg.label.issued_at
                }

            packages_data.append({
                "id": pkg.id,
                "transfer_id": pkg.transfer_id,
                "package_reference": pkg.package_reference,
                "batch_id": pkg.batch_id,
                "manufacturer_lot_number": batch.manufacturer_lot_number if batch else None,
                "expiry_date": batch.expiry_date if batch else None,
                "quantity": pkg.quantity,
                "unit": pkg.unit,
                "status": pkg.status,
                "label": label_data
            })
            total_qty += pkg.quantity

        results.append({
            "id": t.id,
            "proposal_id": t.proposal_id,
            "status": t.status,
            "source_facility_id": t.source_facility_id,
            "source_facility_name": src.name if src else "Unknown",
            "destination_facility_id": t.destination_facility_id,
            "destination_facility_name": dest.name if dest else "Unknown",
            "product_name": prod.name if prod else "Medicine Transfer",
            "quantity": total_qty,
            "unit": packages_data[0]["unit"] if packages_data else "UNIT",
            "tracking_reference": t.tracking_reference,
            "created_at": t.created_at,
            "dispatched_at": t.dispatched_at,
            "received_at": t.received_at,
            "closed_at": t.closed_at,
            "packages": packages_data
        })

    return results


@router.get("/{transfer_id}", response_model=TransferResponse)
def get_transfer(transfer_id: str, db: Session = Depends(get_db)):
    t = db.query(Transfer).filter(Transfer.id == transfer_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Transfer not found")
    all_t = list_transfers(db=db)
    for item in all_t:
        if item.id == transfer_id:
            return item
    raise HTTPException(status_code=404, detail="Transfer not found")


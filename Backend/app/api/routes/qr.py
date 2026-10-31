from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models.transfer import SerializedLabel, TransferPackage, Transfer
from app.models.product import Batch, Product
from app.models.organization import Facility
from app.services.qr_service import QRService
from app.schemas.domain import ScanRequest, ScanResultResponse

router = APIRouter(prefix="/qr", tags=["qr"])


@router.get("/generate-image")
def generate_qr_image(token: str = Query(..., description="The opaque label token")):
    """Generates a high-contrast QR image data URI from a token string."""
    try:
        data_uri = QRService.generate_qr_image_data_uri(token)
        return {"token": token, "data_uri": data_uri}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/scan", response_model=ScanResultResponse)
def process_qr_scan(
    payload: ScanRequest,
    db: Session = Depends(get_db)
):
    """
    Authenticated scan processor.
    Validates token hash against database, enforces facility boundaries,
    rejects replays and duplicate scans, validates transfer context,
    reconciles multi-category quantities, and records atomic ledger transactions.
    """
    try:
        result = QRService.process_scan(
            db=db,
            token=payload.token,
            facility_id=payload.facility_id,
            user_id=payload.user_id,
            scan_type=payload.scan_type,
            idempotency_key=payload.idempotency_key,
            accepted_quantity=payload.accepted_quantity,
            damaged_quantity=payload.damaged_quantity or 0,
            rejected_quantity=payload.rejected_quantity or 0,
            quarantined_quantity=payload.quarantined_quantity or 0,
            expected_transfer_id=payload.expected_transfer_id,
            notes=payload.notes
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan processing error: {str(e)}")


@router.post("/transfers/{transfer_id}/generate-labels")
def generate_transfer_labels(
    transfer_id: str,
    actor_user_id: Optional[str] = Body(None, embed=True),
    db: Session = Depends(get_db)
):
    """
    Creates serialized QR labels for an approved and reserved transfer.
    Only allowed when transfer is in RESERVED or READY_FOR_DISPATCH status.
    """
    try:
        return QRService.generate_labels_for_transfer(
            db=db,
            transfer_id=transfer_id,
            actor_user_id=actor_user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating labels: {str(e)}")


@router.get("/transfers/{transfer_id}/labels")
def get_transfer_labels(
    transfer_id: str,
    db: Session = Depends(get_db)
):
    """Returns packages and serialized label metadata for a transfer."""
    try:
        return QRService.get_transfer_labels(db=db, transfer_id=transfer_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/demo-tokens")
def get_demo_scannable_tokens(db: Session = Depends(get_db)):
    """
    Helper for hackathon testing and live browser camera demo.
    Returns active transfers and their corresponding valid test tokens and QR data URIs.
    """
    tokens = []

    # 1. Pre-seeded demo token for quick UI testing
    tokens.append({
        "transfer_id": "DEMO-001",
        "package_reference": "PKG-DEMO-01",
        "label_status": "ISSUED",
        "token": "SOS_DEMO_TRANSFER_TOKEN_VALID_2026",
        "qr_data_uri": QRService.generate_qr_image_data_uri("SOS_DEMO_TRANSFER_TOKEN_VALID_2026"),
        "source_facility_id": "FAC-001",
        "source_facility": "Apex Memorial Hospital",
        "destination_facility_id": "FAC-002",
        "destination_facility": "Highland Community Hospital",
        "instructions": "Scan at Apex Memorial Hospital for DISPATCH, then scan at Highland Community Hospital for RECEIVE."
    })

    # 2. Check for real transfers in database with packages
    active_transfers = db.query(Transfer).filter(
        Transfer.status.in_(["RESERVED", "READY_FOR_DISPATCH", "DISPATCHED", "IN_TRANSIT", "PARTIALLY_RECEIVED"])
    ).limit(10).all()

    for t in active_transfers:
        src = db.query(Facility).filter(Facility.id == t.source_facility_id).first()
        dest = db.query(Facility).filter(Facility.id == t.destination_facility_id).first()
        src_name = src.name if src else t.source_facility_id
        dest_name = dest.name if dest else t.destination_facility_id

        for pkg in t.packages:
            if pkg.label:
                tokens.append({
                    "transfer_id": t.id,
                    "package_reference": pkg.package_reference,
                    "label_status": pkg.label.status,
                    "label_id": pkg.label.id,
                    "token_hash_preview": f"HASH_{pkg.label.token_hash[:8]}...",
                    "source_facility_id": t.source_facility_id,
                    "source_facility": src_name,
                    "destination_facility_id": t.destination_facility_id,
                    "destination_facility": dest_name,
                    "transfer_status": t.status,
                    "instructions": f"Current status: {pkg.label.status}. Scan at {src_name if pkg.label.status == 'ISSUED' else dest_name}."
                })

    return tokens

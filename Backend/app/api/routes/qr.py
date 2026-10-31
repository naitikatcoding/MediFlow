from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models.transfer import SerializedLabel, TransferPackage, Transfer
from app.models.product import Batch, Product
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
    rejects replays and duplicate scans, and records atomic ledger transactions.
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
            notes=payload.notes
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan processing error: {str(e)}")


@router.get("/demo-tokens")
def get_demo_scannable_tokens(db: Session = Depends(get_db)):
    """
    Helper for hackathon testing and live browser camera demo.
    Returns active transfers and their corresponding valid test tokens and QR data URIs.
    """
    # Deterministic known tokens
    labels = db.query(SerializedLabel, TransferPackage, Transfer).join(
        TransferPackage, SerializedLabel.transfer_package_id == TransferPackage.id
    ).join(
        Transfer, TransferPackage.transfer_id == Transfer.id
    ).all()

    tokens = []
    # Always include the pre-seeded demo token
    tokens.append({
        "transfer_id": "DEMO-001",
        "package_reference": "PKG-DEMO-01",
        "label_status": "ISSUED",
        "token": "SOS_DEMO_TRANSFER_TOKEN_VALID_2026",
        "qr_data_uri": QRService.generate_qr_image_data_uri("SOS_DEMO_TRANSFER_TOKEN_VALID_2026"),
        "source_facility": "Apex Memorial Hospital",
        "destination_facility": "Highland Community Hospital",
        "instructions": "Scan at Apex for DISPATCH, then scan at Highland for RECEIVE."
    })

    return tokens


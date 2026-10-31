from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models.transfer import Transfer, TransferPackage
from app.models.proposal import TransferProposal
from app.models.product import Product
from app.models.organization import Facility
from app.services.transfer_service import (
    TransferLifecycleService, TransferStateMachineError, ReservationConflictError
)

router = APIRouter(prefix="/transfers", tags=["transfers"])


class TransferStateRequest(BaseModel):
    target_status: str = Field(..., description="Target status for this transition")
    actor_user_id: str = Field(..., description="User performing the transition")
    reason: Optional[str] = Field(None)
    metadata: Optional[Dict[str, Any]] = Field(None)


class CancelRequest(BaseModel):
    actor_user_id: str = Field(..., description="User requesting cancellation")
    reason: str = Field(..., min_length=5, description="Reason for cancellation (mandatory)")


class ExpireRequest(BaseModel):
    reason: Optional[str] = Field("Transfer expired due to timeout")


class ReplanRequest(BaseModel):
    actor_user_id: str = Field(..., description="User triggering re-plan")
    reason: Optional[str] = Field("Stock conflict — re-planning triggered")


def _build_transfer_summary(db, transfer):
    """Build lightweight transfer summary row for list responses."""
    prop = db.query(TransferProposal).filter(
        TransferProposal.id == transfer.proposal_id
    ).first()
    src = db.query(Facility).filter(Facility.id == transfer.source_facility_id).first()
    dest = db.query(Facility).filter(Facility.id == transfer.destination_facility_id).first()
    prod = db.query(Product).filter(
        Product.id == prop.product_id
    ).first() if prop else None

    pkgs = db.query(TransferPackage).filter(
        TransferPackage.transfer_id == transfer.id
    ).all()
    total_qty = sum(p.quantity for p in pkgs)
    unit = pkgs[0].unit if pkgs else (prop.unit if prop else "UNIT")

    packages_data = []
    for pkg in pkgs:
        label_info = None
        if pkg.label:
            label_info = {
                "id": pkg.label.id,
                "label_version": pkg.label.label_version,
                "status": pkg.label.status,
                "token_preview": f"HASH_{pkg.label.token_hash[:8]}...",
                "issued_at": pkg.label.issued_at,
            }
        packages_data.append({
            "id": pkg.id,
            "transfer_id": pkg.transfer_id,
            "package_reference": pkg.package_reference,
            "batch_id": pkg.batch_id,
            "manufacturer_lot_number": pkg.batch.manufacturer_lot_number if pkg.batch else None,
            "expiry_date": pkg.batch.expiry_date if pkg.batch else None,
            "quantity": pkg.quantity,
            "unit": pkg.unit,
            "status": pkg.status,
            "label": label_info,
        })

    return {
        "id": transfer.id,
        "proposal_id": transfer.proposal_id,
        "status": transfer.status,
        "source_facility_id": transfer.source_facility_id,
        "source_facility_name": src.name if src else "Unknown",
        "destination_facility_id": transfer.destination_facility_id,
        "destination_facility_name": dest.name if dest else "Unknown",
        "product_name": prod.name if prod else "Medicine Transfer",
        "quantity": total_qty,
        "unit": unit,
        "tracking_reference": transfer.tracking_reference,
        "created_at": transfer.created_at,
        "dispatched_at": transfer.dispatched_at,
        "received_at": transfer.received_at,
        "closed_at": transfer.closed_at,
        "packages": packages_data,
    }


@router.get("")
def list_transfers(
    status: Optional[str] = None,
    facility_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List transfers with optional status and facility filters."""
    query = db.query(Transfer)
    if status:
        query = query.filter(Transfer.status == status)
    if facility_id:
        query = query.filter(
            (Transfer.source_facility_id == facility_id) |
            (Transfer.destination_facility_id == facility_id)
        )
    transfers = query.order_by(Transfer.created_at.desc()).all()
    return [_build_transfer_summary(db, t) for t in transfers]


@router.get("/{transfer_id}")
def get_transfer(transfer_id: str, db: Session = Depends(get_db)):
    """
    Full transfer detail including packages, QR labels, approvals, scan events,
    and complete audit trail.
    """
    detail = TransferLifecycleService.get_transfer_detail(db, transfer_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Transfer {transfer_id} not found.")
    return detail


@router.post("/{transfer_id}/state")
def advance_transfer_state(
    transfer_id: str,
    payload: TransferStateRequest,
    db: Session = Depends(get_db),
):
    """
    Advances a transfer to a new state after validating the allowed transition.
    Invalid transitions are rejected with 400.
    """
    try:
        return TransferLifecycleService.advance_state(
            db=db,
            transfer_id=transfer_id,
            target_status=payload.target_status,
            actor_user_id=payload.actor_user_id,
            reason=payload.reason,
            metadata=payload.metadata,
        )
    except TransferStateMachineError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{transfer_id}/cancel")
def cancel_transfer(
    transfer_id: str,
    payload: CancelRequest,
    db: Session = Depends(get_db),
):
    """
    Cancels a transfer and releases reserved stock via compensating ledger entry (idempotent).
    Only valid from RESERVED or READY_FOR_DISPATCH states.
    """
    try:
        return TransferLifecycleService.cancel_transfer(
            db=db,
            transfer_id=transfer_id,
            actor_user_id=payload.actor_user_id,
            reason=payload.reason,
        )
    except TransferStateMachineError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{transfer_id}/expire")
def expire_transfer(
    transfer_id: str,
    payload: ExpireRequest,
    db: Session = Depends(get_db),
):
    """
    Marks a transfer as EXPIRED. Releases reserved stock exactly once (idempotent).
    Safe to call multiple times.
    """
    try:
        return TransferLifecycleService.expire_transfer(
            db=db,
            transfer_id=transfer_id,
            reason=payload.reason or "Transfer expired due to timeout",
        )
    except TransferStateMachineError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/replan/{proposal_id}")
def trigger_replan(
    proposal_id: str,
    payload: ReplanRequest,
    db: Session = Depends(get_db),
):
    """
    Triggers re-planning for a failed or rejected proposal.
    Bumps proposal_version (invalidating prior approvals) and resets to PROPOSED.
    The matching service should then be called to generate a fresh proposal.
    """
    try:
        return TransferLifecycleService.trigger_replan(
            db=db,
            failed_proposal_id=proposal_id,
            actor_user_id=payload.actor_user_id,
            reason=payload.reason or "Re-planning triggered",
        )
    except TransferStateMachineError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

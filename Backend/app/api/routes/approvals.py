from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.services.transfer_service import (
    ApprovalService, ApprovalError, ReservationConflictError
)

router = APIRouter(prefix="/approvals", tags=["approvals"])


class ApprovalRequest(BaseModel):
    facility_id: str = Field(..., description="ID of the approving facility (source or destination)")
    approver_user_id: str = Field(..., description="ID of the authorised user approving")
    proposal_version: int = Field(..., description="Must match current proposal_version exactly")
    decision: str = Field("APPROVED", description="APPROVED or REJECTED")
    reason: Optional[str] = Field(None, description="Optional reason / clinical justification")
    idempotency_key: Optional[str] = Field(None, description="Optional client idempotency key")


@router.post("/{proposal_id}", response_model=Dict[str, Any])
def record_approval(
    proposal_id: str,
    payload: ApprovalRequest,
    db: Session = Depends(get_db),
):
    """
    Records human approval or rejection for source or destination facility.

    Enforces:
    - Exact proposal_version match (stale approvals rejected)
    - Facility membership: approver must belong to the claimed facility
    - Role check: only authorised roles (PHARMACIST, APPROVER, MEDICAL_SUPERINTENDENT, etc.)
    - No double-approval for same facility + version
    - Cannot approve terminal proposals (RESERVED, REJECTED, CANCELLED, EXPIRED)

    When BOTH parties approve in the same transaction:
    - Triggers concurrency-safe atomic stock reservation with row-level locking
    - Revalidates stock under lock — returns conflict details if stock changed
    - Issues serialized QR labels on success
    """
    try:
        result = ApprovalService.record_approval(
            db=db,
            proposal_id=proposal_id,
            facility_id=payload.facility_id,
            approver_user_id=payload.approver_user_id,
            proposal_version=payload.proposal_version,
            decision=payload.decision,
            reason=payload.reason,
            idempotency_key=payload.idempotency_key,
        )
        return result
    except ApprovalError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ReservationConflictError as e:
        raise HTTPException(status_code=409, detail={
            "error": "RESERVATION_CONFLICT",
            "message": str(e),
            "conflict_details": e.conflict_details,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Approval error: {str(e)}")

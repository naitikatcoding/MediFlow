from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.services.proposal_service import ProposalService
from app.schemas.domain import ProposalApprovalRequest

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.post("/{proposal_id}")
def record_approval(
    proposal_id: str,
    payload: ProposalApprovalRequest,
    db: Session = Depends(get_db)
):
    """
    Records human approval or rejection for source or destination facility.
    Requires exact proposal_version. When both parties approve, triggers atomic
    stock reservation and QR label generation.
    """
    try:
        result = ProposalService.record_approval(
            db=db,
            proposal_id=proposal_id,
            facility_id=payload.facility_id,
            approver_user_id=payload.approver_user_id,
            proposal_version=payload.proposal_version,
            decision=payload.decision,
            reason=payload.reason
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Approval execution error: {str(e)}")


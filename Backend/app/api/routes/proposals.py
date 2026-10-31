from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models.proposal import TransferProposal, TransferProposalBatch, TransferApproval
from app.models.product import Product
from app.models.organization import Facility
from app.services.matching_service import MatchingService
from app.services.proposal_service import ProposalService
from app.schemas.domain import TransferProposalResponse

router = APIRouter(prefix="/proposals", tags=["proposals"])


@router.get("/opportunities")
def list_redistribution_opportunities(
    product_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Returns deterministic matching opportunities across the network,
    including accepted surplus-need pairs and detailed reasons for rejected pairs.
    """
    return MatchingService.find_redistribution_opportunities(db, product_id=product_id)


@router.get("", response_model=List[TransferProposalResponse])
def list_proposals(
    status: Optional[str] = None,
    facility_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(TransferProposal)
    if status:
        query = query.filter(TransferProposal.status == status)
    if facility_id:
        query = query.filter(
            (TransferProposal.source_facility_id == facility_id) |
            (TransferProposal.destination_facility_id == facility_id)
        )
    proposals = query.order_by(TransferProposal.created_at.desc()).all()

    results = []
    for p in proposals:
        src = db.query(Facility).filter(Facility.id == p.source_facility_id).first()
        dest = db.query(Facility).filter(Facility.id == p.destination_facility_id).first()
        prod = db.query(Product).filter(Product.id == p.product_id).first()
        
        # Check approvals
        approvals = db.query(TransferApproval).filter(
            TransferApproval.proposal_id == p.id,
            TransferApproval.proposal_version == p.proposal_version,
            TransferApproval.decision == "APPROVED"
        ).all()
        src_appr = any(a.facility_id == p.source_facility_id for a in approvals)
        dest_appr = any(a.facility_id == p.destination_facility_id for a in approvals)

        batch_items = []
        for pb in p.batches:
            batch_items.append({
                "batch_id": pb.batch_id,
                "manufacturer_lot_number": pb.batch.manufacturer_lot_number,
                "expiry_date": pb.batch.expiry_date,
                "quantity": pb.quantity,
                "unit": pb.unit
            })

        results.append({
            "id": p.id,
            "source_facility_id": p.source_facility_id,
            "source_facility_name": src.name if src else "Unknown",
            "destination_facility_id": p.destination_facility_id,
            "destination_facility_name": dest.name if dest else "Unknown",
            "product_id": p.product_id,
            "product_name": prod.name if prod else "Unknown",
            "proposed_quantity": p.proposed_quantity,
            "unit": p.unit,
            "status": p.status,
            "priority": p.priority,
            "expected_arrival_at": p.expected_arrival_at,
            "source_rationale": p.source_rationale or {},
            "destination_rationale": p.destination_rationale or {},
            "optimisation_metadata": p.optimisation_metadata or {},
            "proposal_version": p.proposal_version,
            "batches": batch_items,
            "source_approved": src_appr,
            "destination_approved": dest_appr,
            "can_reserve": src_appr and dest_appr and p.status in ("APPROVED", "PROPOSED", "PENDING_SOURCE_APPROVAL", "PENDING_DESTINATION_APPROVAL"),
            "created_at": p.created_at
        })
    return results


@router.post("", response_model=Dict[str, Any])
def create_proposal_from_opportunity(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    """Generates an official transfer proposal from an accepted matching candidate."""
    try:
        proposal = ProposalService.create_proposal(
            db=db,
            source_facility_id=payload["source_facility_id"],
            destination_facility_id=payload["destination_facility_id"],
            product_id=payload["product_id"],
            proposed_quantity=payload["matched_quantity"],
            batches=payload["batches"],
            source_rationale=payload.get("source_rationale", {}),
            destination_rationale=payload.get("destination_rationale", {}),
            priority=payload.get("priority", "MEDIUM"),
            unit=payload.get("unit", "UNIT"),
            optimisation_metadata=payload.get("optimisation_metadata")
        )
        return {
            "success": True,
            "proposal_id": proposal.id,
            "status": proposal.status,
            "message": f"Proposal created successfully with version {proposal.proposal_version}."
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


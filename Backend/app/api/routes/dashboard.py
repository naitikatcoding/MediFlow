from typing import Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.api.deps import get_db
from app.models.organization import Facility
from app.models.product import Product
from app.models.proposal import TransferProposal
from app.models.transfer import Transfer
from app.services.risk_service import RiskService
from app.schemas.domain import DashboardOverviewResponse
from app.core.config import settings

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=DashboardOverviewResponse)
def get_dashboard_overview(db: Session = Depends(get_db)):
    """
    Computes live network-wide metrics from transactional state:
    Active facilities, monitored medicines, stockout risks, expiry risks,
    transferable surplus, active proposals, and verified redistributions.
    """
    total_facilities = db.query(func.count(Facility.id)).scalar() or 0
    monitored_products = db.query(func.count(Product.id)).scalar() or 0
    
    # Calculate live risks from domain logic
    all_risks = RiskService.evaluate_risks(db)
    stockout_risks = [r for r in all_risks if r["risk_type"] == "STOCKOUT_RISK"]
    critical_stockouts = [r for r in stockout_risks if r["risk_level"] == "CRITICAL"]
    expiry_risks = [r for r in all_risks if r["risk_type"] == "EXPIRY_RISK"]
    surplus_assessments = [r for r in all_risks if r["risk_type"] == "SURPLUS_AVAILABLE"]
    total_surplus_units = sum(s["at_risk_quantity"] or 0 for s in surplus_assessments)

    # Proposals & Transfers
    active_proposals = db.query(func.count(TransferProposal.id)).filter(
        TransferProposal.status.in_(["PROPOSED", "PENDING_SOURCE_APPROVAL", "PENDING_DESTINATION_APPROVAL", "APPROVED"])
    ).scalar() or 0

    in_transit_transfers = db.query(func.count(Transfer.id)).filter(
        Transfer.status.in_(["IN_TRANSIT", "READY_FOR_DISPATCH", "RESERVED"])
    ).scalar() or 0

    completed_redistributions = db.query(func.count(Transfer.id)).filter(
        Transfer.status.in_(["RECEIVED", "CLOSED"])
    ).scalar() or 0

    return {
        "total_facilities": total_facilities,
        "monitored_products": monitored_products,
        "active_stockout_risks": len(stockout_risks),
        "critical_stockout_risks": len(critical_stockouts),
        "active_expiry_risks": len(expiry_risks),
        "transferable_surplus_units": total_surplus_units,
        "active_proposals": active_proposals,
        "in_transit_transfers": in_transit_transfers,
        "completed_redistributions": completed_redistributions,
        "simulated_wastage_prevented_units": completed_redistributions * 40 + 100,
        "system_mode": "SIMULATION",
        "integrations": {
            "gemini": "LIVE" if settings.GEMINI_API_KEY else "RULE_BASED_SYNTHESIS_ADAPTER",
            "meko": "LIVE_MCP" if settings.MEKO_API_KEY else "LOCAL_DECISION_TRACE_ADAPTER",
            "database": "OPERATIONAL_SOURCE_OF_TRUTH"
        }
    }


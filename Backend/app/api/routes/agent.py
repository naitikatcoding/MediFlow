from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.services.agent_service import StockoutShieldAgentService, MekoAdapter

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/run-cycle")
def trigger_agent_cycle(
    facility_id: Optional[str] = Query(None),
    product_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Triggers bounded multi-agent LangGraph workflow:
    Inventory Monitoring -> Demand Forecast -> Expiry & Risk Review -> Supply Optimisation -> Gemini Structured Synthesis -> Human Approval Pause Checkpoint.
    """
    result = StockoutShieldAgentService.run_inventory_monitoring_cycle(
        db=db,
        facility_id=facility_id,
        product_id=product_id
    )
    return result


@router.get("/traces")
def get_decision_traces(facility_id: Optional[str] = None):
    """Retrieves operational decision traces and shared agent context from the MEKO adapter."""
    if facility_id:
        return MekoAdapter.get_context(facility_id)
    return MekoAdapter._local_memory_store


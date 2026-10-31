"""
MediFlow Multi-Agent Workflow API Routes.
Exposes bounded LangGraph workflow execution, checkpoint resume, and execution trace inspection.
"""
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, Query, Path, Body, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.services.agent_service import MediFlowAgentService
from app.integrations.gemini import gemini_adapter
from app.integrations.meko import meko_adapter

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/run-cycle")
def trigger_agent_cycle(
    facility_id: Optional[str] = Query(None),
    product_id: Optional[str] = Query(None),
    trigger_type: str = Query("MANUAL", alias="trigger_type"),
    db: Session = Depends(get_db)
):
    """
    Triggers bounded multi-agent LangGraph workflow:
    1. Inventory Monitoring -> 2. Demand Forecast -> 3. Expiry & Risk Review ->
    4. Supply Optimisation -> 5. Coordinator (Gemini synthesis, policy validation, proposal creation).
    Pauses at human approval checkpoint if proposal is generated.
    """
    result = MediFlowAgentService.run_workflow_cycle(
        db=db,
        facility_id=facility_id,
        product_id=product_id,
        trigger_event_type=trigger_type
    )
    return result


@router.post("/resume/{workflow_id}")
def resume_workflow(
    workflow_id: str = Path(..., description="ID of the paused workflow run"),
    db: Session = Depends(get_db)
):
    """
    Resumes a paused workflow run after clinical approvals have been recorded.
    Enforces deterministic policy re-validation before stock reservation.
    """
    result = MediFlowAgentService.resume_workflow_approval(db=db, workflow_id=workflow_id)
    if result.get("status") == "ERROR":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.get("message"))
    return result


@router.get("/runs")
def list_workflow_runs(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lists recent multi-agent workflow executions with high-level summaries."""
    return MediFlowAgentService.list_workflow_runs(db=db, limit=limit)


@router.get("/runs/{workflow_id}")
def get_workflow_run_detail(
    workflow_id: str = Path(..., description="ID of the workflow run"),
    db: Session = Depends(get_db)
):
    """Retrieves full execution trace and tool calls for an agent workflow run."""
    run = MediFlowAgentService.get_workflow_run_detail(db=db, workflow_id=workflow_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow run {workflow_id} not found."
        )
    return run


@router.get("/traces")
def get_decision_traces(
    facility_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100)
):
    """Retrieves operational decision traces and shared agent context from the MEKO adapter."""
    records = meko_adapter.retrieve_context(facility_id=facility_id, limit=limit)
    return records


@router.get("/status")
def get_agent_system_status():
    """Returns runtime status of external intelligence integrations (Gemini and MEKO)."""
    return {
        "gemini": gemini_adapter.get_status(),
        "meko": meko_adapter.get_status()
    }

"""
MediFlow Typed Agent Workflow State and Pydantic Schemas.
Enforces strict boundaries between agent reasoning and deterministic authority.
"""
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Literal
from typing_extensions import TypedDict
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────
# PYDANTIC SCHEMAS FOR STRUCTURED GEMINI OUTPUT & OBSERVATIONS
# ─────────────────────────────────────────────────────────────────

class GeminiStructuredAnalysis(BaseModel):
    """
    Structured reasoning output requested from Gemini.
    Validated as untrusted input.
    """
    clinical_operational_summary: str = Field(
        ...,
        description="Concise summary of the supply condition, strictly grounded in provided tool facts."
    )
    key_risk_drivers: List[str] = Field(
        default_factory=list,
        description="Identified risk drivers (e.g. lead-time breach, near-expiry batch, stockout date)."
    )
    recommended_action: str = Field(
        ...,
        description="Non-binding operational recommendation for human reviewers."
    )
    uncertainty_notes: List[str] = Field(
        default_factory=list,
        description="Surfaced uncertainties, such as missing consumption weeks or data freshness lag."
    )
    missing_fields_detected: List[str] = Field(
        default_factory=list,
        description="Any missing facts, parameters, or unconfirmed delivery dates."
    )
    confidence_assessment: str = Field(
        default="MODERATE",
        description="Agent self-assessed confidence level: HIGH, MODERATE, LOW."
    )


class AgentObservation(BaseModel):
    """Observation recorded by a specialist node."""
    agent_name: str
    summary: str
    key_findings: List[str] = Field(default_factory=list)
    uncertainties: List[str] = Field(default_factory=list)
    data_quality_flags: List[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class NodeTraceItem(BaseModel):
    """Trace entry representing one node's execution in the graph."""
    node_name: str
    started_at: str
    completed_at: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    observation: Optional[Dict[str, Any]] = None
    status: Literal["SUCCESS", "FAILED", "SKIPPED", "PAUSED"] = "SUCCESS"
    error: Optional[str] = None


# ─────────────────────────────────────────────────────────────────
# TYPEDDICT WORKFLOW STATE FOR LANGGRAPH
# ─────────────────────────────────────────────────────────────────

class AgentGraphState(TypedDict, total=False):
    # Core identifiers
    workflow_id: str
    trigger_event_type: str  # MANUAL, RISK_ALERT, SCHEDULED
    trigger_event_id: Optional[str]
    facility_scope: Optional[str]
    product_scope: Optional[str]

    # Data Quality & Inventory (Inventory Monitoring Agent)
    data_quality_status: Dict[str, Any]
    inventory_summary: List[Dict[str, Any]]

    # Forecast Signals (Demand Forecast Agent)
    forecast_run_id: Optional[str]
    forecast_summary: Dict[str, Any]

    # Risk Evaluations (Expiry and Risk Agent)
    risk_assessment_id: Optional[str]
    stockout_risks: List[Dict[str, Any]]
    expiry_risks: List[Dict[str, Any]]

    # Supply Optimisation (Supply Optimisation Agent)
    candidate_pairs: List[Dict[str, Any]]
    optimisation_result: Optional[Dict[str, Any]]
    optimisation_result_id: Optional[str]

    # Proposal & Policy (Orchestrator Node)
    proposal_id: Optional[str]
    proposal_version: Optional[int]
    policy_validation: Dict[str, Any]

    # Human-In-The-Loop Approval & Handoff
    approval_status: Dict[str, Any]
    transfer_id: Optional[str]
    pause_for_human_approval: bool

    # Shared Context & Intelligence
    meko_context: List[Dict[str, Any]]
    meko_status: str  # LIVE, LOCAL_FALLBACK, UNAVAILABLE
    gemini_analysis: Dict[str, Any]
    gemini_status: str  # LIVE, FALLBACK, ERROR, SKIPPED

    # Audit & Traces
    agent_observations: Dict[str, Any]
    node_trace: List[Dict[str, Any]]
    decision_trace_ids: List[str]
    exception_list: List[Dict[str, Any]]
    workflow_status: str
    # RUNNING | PAUSED_FOR_APPROVAL | RESUMED | COMPLETED | FAILED | COMPLETED_NO_ACTIONS


# Backward compatibility alias
AgentState = AgentGraphState

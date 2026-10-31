"""
AgentWorkflowRun — persisted record for each LangGraph workflow execution.
Stores node-level trace, tool calls, MEKO context references, and final proposal.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, DateTime, ForeignKey,
    Text, Boolean, JSON, Index
)
from app.core.database import Base
from app.models.organization import generate_uuid, utc_now


class AgentWorkflowRun(Base):
    """
    Persisted record of one bounded agentic workflow run.
    Status lifecycle: RUNNING -> PAUSED_FOR_APPROVAL -> RESUMED -> COMPLETED | FAILED | CANCELLED
    """
    __tablename__ = "agent_workflow_runs"

    id = Column(String(36), primary_key=True, default=generate_uuid)

    # Trigger context
    trigger_event_type = Column(String(64), nullable=False, default="MANUAL")  # MANUAL, SCHEDULED, RISK_ALERT
    trigger_event_id = Column(String(64), nullable=True)
    facility_scope = Column(String(36), nullable=True, index=True)
    product_scope = Column(String(36), nullable=True, index=True)

    # Status
    workflow_status = Column(String(64), nullable=False, default="RUNNING", index=True)
    # RUNNING | PAUSED_FOR_APPROVAL | RESUMED | COMPLETED | FAILED | CANCELLED | COMPLETED_NO_ACTIONS

    # Linked records
    forecast_run_id = Column(String(36), nullable=True)
    risk_assessment_id = Column(String(36), nullable=True)
    proposal_id = Column(String(36), nullable=True)
    transfer_id = Column(String(36), nullable=True)

    # Structured agent state snapshots
    data_quality_status = Column(JSON, nullable=True)       # {stale: [], missing: [], duplicate: []}
    candidate_pairs = Column(JSON, nullable=True)           # [{source_id, dest_id, quantity, score}]
    optimisation_result = Column(JSON, nullable=True)       # best match details
    policy_validation = Column(JSON, nullable=True)         # {passed: bool, checks: [...]}
    approval_status = Column(JSON, nullable=True)           # {source: APPROVED, destination: PENDING}
    exception_list = Column(JSON, nullable=True, default=list)  # [{node, error, timestamp}]

    # Agent observations (per-node notes)
    agent_observations = Column(JSON, nullable=True, default=dict)
    # { "inventory_monitor": {...}, "demand_forecast": {...}, ... }

    # Gemini / LLM result metadata
    gemini_status = Column(String(32), nullable=True)       # LIVE | FALLBACK | SKIPPED | ERROR
    gemini_model = Column(String(64), nullable=True)

    # MEKO context
    meko_status = Column(String(32), nullable=True)         # LIVE | LOCAL_FALLBACK | UNAVAILABLE
    meko_context_refs = Column(JSON, nullable=True)         # [{ref_id, summary, retrieved_at}]

    # Full node-level trace (for the UI trace view)
    node_trace = Column(JSON, nullable=True, default=list)
    # [{node, started_at, ended_at, tool_calls: [{tool, input_summary, output_summary}], observation, status}]

    # Decision trace IDs (references to MEKO / local store)
    decision_trace_ids = Column(JSON, nullable=True, default=list)

    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_workflow_status_created", "workflow_status", "created_at"),
        Index("ix_workflow_facility_product", "facility_scope", "product_scope"),
    )


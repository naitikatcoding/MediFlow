"""
MediFlow Agent Service.

Orchestrates multi-agent LangGraph workflows, manages human-in-the-loop checkpoints,
persists workflow run records with full trace fidelity, and enforces deterministic
policy re-validation before stock reservation.
"""
import logging
from datetime import datetime, timezone, date
from typing import Dict, Any, List, Optional
from uuid import uuid4
from sqlalchemy.orm import Session

from app.models.workflow import AgentWorkflowRun
from app.models.proposal import TransferProposal, TransferApproval
from app.agents.state import AgentGraphState
from app.agents.graph import create_agent_graph
from app.agents import tools
from app.integrations.gemini import gemini_adapter
from app.integrations.meko import meko_adapter
from app.services.proposal_service import ProposalService

logger = logging.getLogger("mediflow.agent.service")


def _make_json_serializable(obj: Any) -> Any:
    """Recursively converts date, datetime, and set objects to JSON-serializable types."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, set):
        return [_make_json_serializable(v) for v in obj]
    if isinstance(obj, dict):
        return {str(k): _make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_json_serializable(v) for v in obj]
    return obj


class MediFlowAgentService:
    """
    Service coordinating LangGraph workflow runs, pause/resume lifecycles,
    and database persistence of agent execution traces.
    """

    @staticmethod
    def run_workflow_cycle(
        db: Session,
        facility_id: Optional[str] = None,
        product_id: Optional[str] = None,
        trigger_event_type: str = "MANUAL",
        trigger_event_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes a bounded multi-agent cycle:
        1. Inventory Monitoring -> 2. Demand Forecast -> 3. Expiry Risk ->
        4. Supply Optimisation -> 5. Coordinator (Gemini synthesis, policy validation, proposal creation).
        Pauses for human approval if proposal created.
        """
        workflow_id = str(uuid4())

        # Create persisted run record
        run_record = AgentWorkflowRun(
            id=workflow_id,
            trigger_event_type=trigger_event_type,
            trigger_event_id=trigger_event_id,
            facility_scope=facility_id,
            product_scope=product_id,
            workflow_status="RUNNING"
        )
        db.add(run_record)
        db.commit()

        initial_state: AgentGraphState = {
            "workflow_id": workflow_id,
            "trigger_event_type": trigger_event_type,
            "trigger_event_id": trigger_event_id,
            "facility_scope": facility_id,
            "product_scope": product_id,
            "data_quality_status": {},
            "inventory_summary": [],
            "forecast_run_id": None,
            "forecast_summary": {},
            "risk_assessment_id": None,
            "stockout_risks": [],
            "expiry_risks": [],
            "candidate_pairs": [],
            "optimisation_result": None,
            "optimisation_result_id": None,
            "proposal_id": None,
            "proposal_version": None,
            "policy_validation": {},
            "approval_status": {},
            "transfer_id": None,
            "pause_for_human_approval": False,
            "meko_context": [],
            "meko_status": "PENDING",
            "gemini_analysis": {},
            "gemini_status": "PENDING",
            "agent_observations": {},
            "node_trace": [],
            "decision_trace_ids": [],
            "exception_list": [],
            "workflow_status": "RUNNING"
        }

        try:
            # Compile and execute graph
            graph = create_agent_graph(db=db)
            final_state = graph.invoke(
                initial_state,
                config={"configurable": {"thread_id": workflow_id}}
            )

            # Update persisted run record with JSON-safe serializable dictionaries
            run_record.workflow_status = final_state.get("workflow_status", "COMPLETED")
            run_record.forecast_run_id = final_state.get("forecast_run_id")
            run_record.risk_assessment_id = final_state.get("risk_assessment_id")
            run_record.proposal_id = final_state.get("proposal_id")
            run_record.data_quality_status = _make_json_serializable(final_state.get("data_quality_status"))
            run_record.candidate_pairs = _make_json_serializable(final_state.get("candidate_pairs"))
            run_record.optimisation_result = _make_json_serializable(final_state.get("optimisation_result"))
            run_record.policy_validation = _make_json_serializable(final_state.get("policy_validation"))
            run_record.approval_status = _make_json_serializable(final_state.get("approval_status"))
            run_record.agent_observations = _make_json_serializable(final_state.get("agent_observations"))
            run_record.gemini_status = final_state.get("gemini_status")
            run_record.gemini_model = final_state.get("gemini_analysis", {}).get("model")
            run_record.meko_status = final_state.get("meko_status")
            run_record.meko_context_refs = _make_json_serializable(final_state.get("meko_context"))
            run_record.node_trace = _make_json_serializable(final_state.get("node_trace"))
            run_record.exception_list = _make_json_serializable(final_state.get("exception_list", []))

            if run_record.workflow_status in ("COMPLETED", "COMPLETED_NO_ACTIONS", "FAILED"):
                run_record.completed_at = datetime.now(timezone.utc)

            db.commit()
            return final_state

        except Exception as exc:
            logger.exception(f"Workflow {workflow_id} failed with error: {exc}")
            run_record.workflow_status = "FAILED"
            run_record.exception_list = [{"node": "graph_execution", "error": str(exc), "timestamp": datetime.now(timezone.utc).isoformat()}]
            db.commit()
            initial_state["workflow_status"] = "FAILED"
            initial_state["exception_list"] = run_record.exception_list
            return initial_state

    @staticmethod
    def resume_workflow_approval(db: Session, workflow_id: str) -> Dict[str, Any]:
        """
        Resumes a paused workflow once human approval has been recorded.
        1. Checks approval status for exact proposal version.
        2. Re-validates policy and available stock before reservation.
        3. Executes reservation deterministically if re-validation passes.
        """
        run = db.query(AgentWorkflowRun).filter(AgentWorkflowRun.id == workflow_id).first()
        if not run:
            return {"status": "ERROR", "message": f"Workflow run {workflow_id} not found."}

        proposal_id = run.proposal_id
        if not proposal_id:
            return {"status": "ERROR", "message": "Workflow has no associated proposal."}

        proposal = db.query(TransferProposal).filter(TransferProposal.id == proposal_id).first()
        if not proposal:
            return {"status": "ERROR", "message": f"Proposal {proposal_id} not found."}

        # Check approval status
        appr_status = tools.get_approval_status(db, proposal_id)
        run.approval_status = _make_json_serializable(appr_status)

        if not appr_status.get("fully_approved"):
            return {
                "status": "PAUSED_AWAITING_APPROVALS",
                "message": "Both source and destination clinical approvals are required before resuming reservation.",
                "approval_status": appr_status,
                "workflow_status": run.workflow_status
            }

        # RE-VALIDATE POLICY AND USABLE STOCK BEFORE RESERVATION
        # (Guard against concurrent stock depletion between approval and reservation)
        batches_payload = [{"batch_id": b.batch_id, "quantity": b.quantity} for b in proposal.batches]
        reval = tools.validate_transfer_proposal(
            db=db,
            source_facility_id=proposal.source_facility_id,
            destination_facility_id=proposal.destination_facility_id,
            product_id=proposal.product_id,
            quantity=proposal.proposed_quantity,
            batches=batches_payload
        )

        if not reval.get("passed"):
            # Stock changed or batch became ineligible!
            warning_msg = f"Re-validation failed before reservation: {reval.get('checks')}"
            logger.warning(warning_msg)
            run.workflow_status = "FAILED_REVALIDATION"
            run.exception_list = (run.exception_list or []) + [{
                "node": "revalidate_before_reservation",
                "error": warning_msg,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }]
            db.commit()
            return {
                "status": "FAILED_REVALIDATION",
                "message": "Pre-reservation policy revalidation failed. Stock changed or condition breached.",
                "revalidation_details": reval
            }

        # Execute reservation deterministically
        try:
            res_result = ProposalService.reserve_stock_and_issue_labels(db, proposal)
            run.workflow_status = "COMPLETED"
            run.completed_at = datetime.now(timezone.utc)
            db.commit()

            # Record in MEKO
            meko_adapter.record_decision_trace({
                "action": "WORKFLOW_RESUMED_RESERVATION_COMPLETED",
                "workflow_id": workflow_id,
                "proposal_id": proposal_id,
                "status": "COMPLETED"
            })

            return {
                "status": "COMPLETED",
                "message": "Proposal fully approved and stock reserved.",
                "reservation_result": res_result,
                "workflow_id": workflow_id
            }
        except Exception as exc:
            logger.exception("Reservation failed upon resume")
            run.workflow_status = "FAILED_RESERVATION"
            db.commit()
            return {
                "status": "FAILED_RESERVATION",
                "message": str(exc),
                "workflow_id": workflow_id
            }

    @staticmethod
    def list_workflow_runs(db: Session, limit: int = 20) -> List[Dict[str, Any]]:
        """Returns recent workflow execution records for UI trace views."""
        runs = (
            db.query(AgentWorkflowRun)
            .order_by(AgentWorkflowRun.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "workflow_id": r.id,
                "trigger_event_type": r.trigger_event_type,
                "facility_scope": r.facility_scope,
                "product_scope": r.product_scope,
                "workflow_status": r.workflow_status,
                "proposal_id": r.proposal_id,
                "gemini_status": r.gemini_status,
                "gemini_model": r.gemini_model,
                "meko_status": r.meko_status,
                "node_count": len(r.node_trace or []),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in runs
        ]

    @staticmethod
    def get_workflow_run_detail(db: Session, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Returns full fidelity trace for a specific workflow run."""
        r = db.query(AgentWorkflowRun).filter(AgentWorkflowRun.id == workflow_id).first()
        if not r:
            return None
        return {
            "workflow_id": r.id,
            "trigger_event_type": r.trigger_event_type,
            "facility_scope": r.facility_scope,
            "product_scope": r.product_scope,
            "workflow_status": r.workflow_status,
            "proposal_id": r.proposal_id,
            "data_quality_status": r.data_quality_status,
            "candidate_pairs": r.candidate_pairs,
            "optimisation_result": r.optimisation_result,
            "policy_validation": r.policy_validation,
            "approval_status": r.approval_status,
            "agent_observations": r.agent_observations,
            "gemini_status": r.gemini_status,
            "gemini_model": r.gemini_model,
            "meko_status": r.meko_status,
            "meko_context_refs": r.meko_context_refs,
            "node_trace": r.node_trace or [],
            "exception_list": r.exception_list or [],
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }

    # Backward compatibility
    @staticmethod
    def run_inventory_monitoring_cycle(
        db: Session,
        facility_id: Optional[str] = None,
        product_id: Optional[str] = None
    ) -> Dict[str, Any]:
        return MediFlowAgentService.run_workflow_cycle(
            db=db,
            facility_id=facility_id,
            product_id=product_id,
            trigger_event_type="MANUAL"
        )


# Backward compatibility export
MekoAdapter = meko_adapter

"""
MediFlow LangGraph Multi-Agent Workflow Engine.

Coordinates bounded specialist agents:
1. Inventory Monitoring Agent (flags anomalies & freshness)
2. Demand Forecast Agent (calls deterministic WMA forecast)
3. Expiry and Risk Agent (reviews stockout & FEFO expiry)
4. Supply Optimisation Agent (computes candidate redistribution pairs)
5. Orchestrator / Network Coordinator (synthesizes evidence, validates policy, creates proposal, pauses for human approval)
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from uuid import uuid4
from sqlalchemy.orm import Session

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.agents.state import AgentGraphState, AgentObservation, NodeTraceItem
from app.agents import tools
from app.integrations.gemini import gemini_adapter
from app.integrations.meko import meko_adapter

logger = logging.getLogger("mediflow.agent.graph")


def create_agent_graph(db: Session, memory_saver: Optional[MemorySaver] = None):
    """
    Compiles the bounded multi-agent LangGraph workflow.
    """

    # ─────────────────────────────────────────────────────────────
    # NODE 1: Inventory Monitoring Agent
    # ─────────────────────────────────────────────────────────────
    def node_inventory_monitor(state: AgentGraphState) -> AgentGraphState:
        started_at = datetime.now(timezone.utc).isoformat()
        fac_id = state.get("facility_scope")
        prod_id = state.get("product_scope")

        # Execute deterministic inventory inspection tool
        inv_tool_res = tools.get_facility_inventory(db, facility_id=fac_id, product_id=prod_id)

        stale_count = len(inv_tool_res.get("data_quality", {}).get("stale_records", []))
        missing_count = inv_tool_res.get("data_quality", {}).get("missing_quantity_count", 0)
        near_expiry_count = len(inv_tool_res.get("data_quality", {}).get("near_expiry_batches", []))

        flags = []
        if stale_count > 0:
            flags.append(f"{stale_count} batches have stale reporting timestamps (>24h lag).")
        if missing_count > 0:
            flags.append(f"{missing_count} batch records have missing quantity balances.")
        if near_expiry_count > 0:
            flags.append(f"{near_expiry_count} batches are expiring within 60 days.")

        state["data_quality_status"] = {
            "status": "CAUTION" if flags else "HEALTHY",
            "flags": flags,
            "stale_count": stale_count,
            "missing_count": missing_count,
            "near_expiry_count": near_expiry_count,
            "total_records": inv_tool_res.get("record_count", 0)
        }
        state["inventory_summary"] = inv_tool_res.get("records", [])[:15]

        observation = AgentObservation(
            agent_name="Inventory Monitoring Agent",
            summary=f"Evaluated {inv_tool_res.get('record_count', 0)} inventory lots across facility scope.",
            key_findings=[
                f"Active lot records verified: {inv_tool_res.get('record_count', 0)}.",
                f"Data quality health rating: {'CAUTION' if flags else 'HEALTHY'}."
            ],
            uncertainties=[f"Data freshness lag detected in {stale_count} lots."] if stale_count else [],
            data_quality_flags=flags
        )

        trace = NodeTraceItem(
            node_name="Inventory Monitoring Agent",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            tool_calls=[{
                "tool": "get_facility_inventory",
                "inputs": {"facility_id": fac_id, "product_id": prod_id},
                "summary": f"Inspected {inv_tool_res.get('record_count', 0)} lots; {len(flags)} quality flags."
            }],
            observation=observation.model_dump(),
            status="SUCCESS"
        )

        state.setdefault("agent_observations", {})["inventory_monitor"] = observation.model_dump()
        state.setdefault("node_trace", []).append(trace.model_dump())

        # Record in MEKO
        meko_adapter.record_decision_trace({
            "action": "INVENTORY_MONITORED",
            "workflow_id": state.get("workflow_id"),
            "records_evaluated": inv_tool_res.get("record_count", 0),
            "flags_count": len(flags)
        })

        return state

    # ─────────────────────────────────────────────────────────────
    # NODE 2: Demand Forecast Agent
    # ─────────────────────────────────────────────────────────────
    def node_demand_forecast(state: AgentGraphState) -> AgentGraphState:
        started_at = datetime.now(timezone.utc).isoformat()
        fac_id = state.get("facility_scope")
        prod_id = state.get("product_scope")

        tool_calls = []
        forecast_res: Dict[str, Any] = {}
        history_res: Dict[str, Any] = {}

        if fac_id and prod_id:
            # Check consumption history
            history_res = tools.get_consumption_history(db, fac_id, prod_id, weeks=12)
            tool_calls.append({
                "tool": "get_consumption_history",
                "inputs": {"facility_id": fac_id, "product_id": prod_id, "weeks": 12},
                "summary": f"Found {history_res.get('weeks_found', 0)} weeks history. Sufficient: {history_res.get('has_sufficient_history')}."
            })

            # Calculate deterministic forecast
            forecast_res = tools.run_demand_forecast(db, fac_id, prod_id, horizon_days=30)
            tool_calls.append({
                "tool": "run_demand_forecast",
                "inputs": {"facility_id": fac_id, "product_id": prod_id, "horizon_days": 30},
                "summary": f"Daily average: {forecast_res.get('daily_average_demand', 0.0):.2f}; 30d demand: {forecast_res.get('demand_30d', 0.0):.1f}; confidence: {forecast_res.get('confidence_score', 0.0):.2f}."
            })
            state["forecast_run_id"] = forecast_res.get("forecast_id")
        else:
            forecast_res = {
                "model_name": "WEIGHTED_MOVING_AVERAGE",
                "daily_average_demand": 0.0,
                "demand_7d": 0.0,
                "demand_30d": 0.0,
                "confidence_score": 0.85,
                "warnings": ["Network-wide scope without single product target."]
            }

        state["forecast_summary"] = forecast_res

        daily_demand = forecast_res.get("daily_average_demand", 0.0)
        confidence = forecast_res.get("confidence_score", 0.0)
        uncertainties = list(forecast_res.get("warnings", []))
        if history_res.get("missing_weeks", 0) > 0:
            uncertainties.append(f"{history_res.get('missing_weeks')} historical consumption weeks missing.")

        observation = AgentObservation(
            agent_name="Demand Forecast Agent",
            summary=f"Forecast baseline computed via {forecast_res.get('model_name', 'WMA')}. Daily average: {daily_demand:.2f} {forecast_res.get('unit', 'units')}/day.",
            key_findings=[
                f"7-day projected demand: {forecast_res.get('demand_7d', 0.0):.1f}.",
                f"30-day projected demand: {forecast_res.get('demand_30d', 0.0):.1f}.",
                f"Confidence metric: {confidence:.2f}."
            ],
            uncertainties=uncertainties,
            data_quality_flags=list(forecast_res.get("warnings", []))
        )

        trace = NodeTraceItem(
            node_name="Demand Forecast Agent",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            tool_calls=tool_calls,
            observation=observation.model_dump(),
            status="SUCCESS"
        )

        state.setdefault("agent_observations", {})["demand_forecast"] = observation.model_dump()
        state.setdefault("node_trace", []).append(trace.model_dump())
        return state

    # ─────────────────────────────────────────────────────────────
    # NODE 3: Expiry and Risk Agent
    # ─────────────────────────────────────────────────────────────
    def node_expiry_risk(state: AgentGraphState) -> AgentGraphState:
        started_at = datetime.now(timezone.utc).isoformat()
        fac_id = state.get("facility_scope")
        prod_id = state.get("product_scope")

        tool_calls = []

        # Tool: stockout risk
        stockout_res = tools.calculate_stockout_risk(db, facility_id=fac_id or "", product_id=prod_id or "")
        tool_calls.append({
            "tool": "calculate_stockout_risk",
            "inputs": {"facility_id": fac_id, "product_id": prod_id},
            "summary": f"Detected {stockout_res.get('stockout_risks_found', 0)} stockout risk alerts. Critical: {stockout_res.get('has_critical_stockout')}."
        })

        # Tool: expiry risk
        expiry_res = tools.calculate_expiry_risk(db, facility_id=fac_id or "", product_id=prod_id or "")
        tool_calls.append({
            "tool": "calculate_expiry_risk",
            "inputs": {"facility_id": fac_id, "product_id": prod_id},
            "summary": f"Detected {expiry_res.get('expiry_risks_found', 0)} expiry risk alerts. Critical: {expiry_res.get('has_critical_expiry')}."
        })

        state["stockout_risks"] = stockout_res.get("risks", [])
        state["expiry_risks"] = expiry_res.get("risks", [])

        crit_stockout = stockout_res.get("has_critical_stockout", False)
        crit_expiry = expiry_res.get("has_critical_expiry", False)

        observation = AgentObservation(
            agent_name="Expiry and Risk Agent",
            summary=(
                f"Risk review completed. Stockout risks: {stockout_res.get('stockout_risks_found', 0)} "
                f"(Critical: {crit_stockout}), Expiry risks: {expiry_res.get('expiry_risks_found', 0)} "
                f"(Critical: {crit_expiry})."
            ),
            key_findings=[
                f"Critical stockout condition: {'YES' if crit_stockout else 'NO'}.",
                f"Critical near-expiry unconsumed batches: {'YES' if crit_expiry else 'NO'}."
            ],
            uncertainties=[],
            data_quality_flags=[]
        )

        trace = NodeTraceItem(
            node_name="Expiry and Risk Agent",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            tool_calls=tool_calls,
            observation=observation.model_dump(),
            status="SUCCESS"
        )

        state.setdefault("agent_observations", {})["expiry_risk"] = observation.model_dump()
        state.setdefault("node_trace", []).append(trace.model_dump())
        return state

    # ─────────────────────────────────────────────────────────────
    # NODE 4: Supply Optimisation Agent
    # ─────────────────────────────────────────────────────────────
    def node_supply_optimization(state: AgentGraphState) -> AgentGraphState:
        started_at = datetime.now(timezone.utc).isoformat()
        prod_id = state.get("product_scope")

        # Find candidate pairs across network
        candidates_res = tools.find_candidate_facilities(db, product_id=prod_id)
        accepted_pairs = candidates_res.get("pairs", [])
        state["candidate_pairs"] = accepted_pairs

        best_option = None
        tool_calls = [{
            "tool": "find_candidate_facilities",
            "inputs": {"product_id": prod_id},
            "summary": f"Found {len(accepted_pairs)} accepted pairs, {candidates_res.get('rejected_candidates', 0)} rejections."
        }]

        if accepted_pairs:
            top_pair = accepted_pairs[0]
            src_id = top_pair.get("source_facility_id")
            dst_id = top_pair.get("destination_facility_id")
            p_id = top_pair.get("product_id") or prod_id

            if src_id and dst_id and p_id:
                calc_res = tools.calculate_transfer_options(db, src_id, dst_id, p_id)
                tool_calls.append({
                    "tool": "calculate_transfer_options",
                    "inputs": {"source_facility_id": src_id, "destination_facility_id": dst_id, "product_id": p_id},
                    "summary": f"Calculated transfer: {calc_res.get('eligible_transfer_quantity', 0)} units feasible."
                })
                if calc_res.get("feasible") and calc_res.get("eligible_transfer_quantity", 0) > 0:
                    best_option = {
                        "source_facility_id": src_id,
                        "source_facility_name": top_pair.get("source_facility_name"),
                        "destination_facility_id": dst_id,
                        "destination_facility_name": top_pair.get("destination_facility_name"),
                        "product_id": p_id,
                        "product_name": top_pair.get("product_name"),
                        "proposed_quantity": calc_res.get("eligible_transfer_quantity"),
                        "candidate_surplus": calc_res.get("candidate_surplus"),
                        "destination_unmet_need": calc_res.get("destination_unmet_need"),
                        "destination_days_of_cover": top_pair.get("destination_days_of_cover", 0.0),
                        "fefo_batches": calc_res.get("fefo_batches", []),
                        "score": top_pair.get("score", 95.0)
                    }

        state["optimisation_result"] = best_option
        if best_option:
            state["optimisation_result_id"] = str(uuid4())

        observation = AgentObservation(
            agent_name="Supply Optimisation Agent",
            summary=(
                f"Evaluated {len(accepted_pairs)} candidate redistribution pairs. "
                f"Selected optimal match: {best_option.get('proposed_quantity', 0) if best_option else 0} units "
                f"from {best_option.get('source_facility_name', 'None') if best_option else 'None'} to "
                f"{best_option.get('destination_facility_name', 'None') if best_option else 'None'}."
            ),
            key_findings=[
                f"Viable candidate pairs: {len(accepted_pairs)}.",
                f"Optimal match feasible: {'YES' if best_option else 'NO'}."
            ],
            uncertainties=[],
            data_quality_flags=[]
        )

        trace = NodeTraceItem(
            node_name="Supply Optimisation Agent",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            tool_calls=tool_calls,
            observation=observation.model_dump(),
            status="SUCCESS"
        )

        state.setdefault("agent_observations", {})["supply_optimization"] = observation.model_dump()
        state.setdefault("node_trace", []).append(trace.model_dump())
        return state

    # ─────────────────────────────────────────────────────────────
    # NODE 5: Orchestrator / Network Coordinator
    # ─────────────────────────────────────────────────────────────
    def node_orchestrator(state: AgentGraphState) -> AgentGraphState:
        started_at = datetime.now(timezone.utc).isoformat()
        best_match = state.get("optimisation_result")
        tool_calls = []

        # Step 1: Retrieve shared context from MEKO
        meko_ctx = meko_adapter.retrieve_context(
            facility_id=state.get("facility_scope"),
            product_id=state.get("product_scope"),
            limit=3
        )
        state["meko_context"] = meko_ctx
        state["meko_status"] = meko_adapter.get_status()["mode"]
        tool_calls.append({
            "tool": "meko_retrieve_context",
            "inputs": {"facility_id": state.get("facility_scope")},
            "summary": f"Retrieved {len(meko_ctx)} contextual operational records ({state['meko_status']})."
        })

        # Step 2: Gemini structured reasoning synthesis
        facts_for_gemini = {
            "workflow_id": state.get("workflow_id"),
            "data_quality": state.get("data_quality_status"),
            "forecast": state.get("forecast_summary"),
            "stockout_risks_count": len(state.get("stockout_risks", [])),
            "expiry_risks_count": len(state.get("expiry_risks", [])),
            "match": best_match
        }
        gemini_res = gemini_adapter.generate_structured_analysis(
            context_type="REDISTRIBUTION_PROPOSAL" if best_match else "NETWORK_MONITORING_CYCLE",
            facts=facts_for_gemini,
            uncertainties=state.get("forecast_summary", {}).get("warnings", []),
            data_quality_flags=state.get("data_quality_status", {}).get("flags", [])
        )
        state["gemini_analysis"] = gemini_res
        state["gemini_status"] = gemini_res.get("status", "FALLBACK")
        tool_calls.append({
            "tool": "gemini_generate_structured_analysis",
            "inputs": {"context_type": "REDISTRIBUTION_PROPOSAL" if best_match else "NETWORK_CYCLE"},
            "summary": f"Reasoning produced via {gemini_res.get('source')} ({gemini_res.get('model')}). Live: {gemini_res.get('gemini_live_executed')}."
        })

        # Step 3: Proposal Policy Validation & Creation
        if best_match and best_match.get("proposed_quantity", 0) > 0:
            val_res = tools.validate_transfer_proposal(
                db=db,
                source_facility_id=best_match["source_facility_id"],
                destination_facility_id=best_match["destination_facility_id"],
                product_id=best_match["product_id"],
                quantity=best_match["proposed_quantity"],
                batches=best_match.get("fefo_batches", [])
            )
            state["policy_validation"] = val_res
            tool_calls.append({
                "tool": "validate_transfer_proposal",
                "inputs": {"quantity": best_match["proposed_quantity"]},
                "summary": f"Policy validation: Passed={val_res.get('passed')}. Checks={val_res.get('check_count')}."
            })

            if val_res.get("passed"):
                # Create transfer proposal deterministically
                prop_res = tools.create_transfer_proposal(
                    db=db,
                    source_facility_id=best_match["source_facility_id"],
                    destination_facility_id=best_match["destination_facility_id"],
                    product_id=best_match["product_id"],
                    quantity=best_match["proposed_quantity"],
                    batches=best_match.get("fefo_batches", []),
                    source_rationale={
                        "candidate_surplus": best_match.get("candidate_surplus"),
                        "analysis": gemini_res.get("structured_analysis", {}).get("clinical_operational_summary")
                    },
                    destination_rationale={
                        "destination_unmet_need": best_match.get("destination_unmet_need"),
                        "destination_days_of_cover": best_match.get("destination_days_of_cover"),
                        "action": gemini_res.get("structured_analysis", {}).get("recommended_action")
                    },
                    workflow_id=state.get("workflow_id"),
                    priority="HIGH" if best_match.get("destination_days_of_cover", 0) <= 7 else "MEDIUM"
                )
                tool_calls.append({
                    "tool": "create_transfer_proposal",
                    "inputs": {"quantity": best_match["proposed_quantity"]},
                    "summary": f"Created proposal ID: {prop_res.get('proposal_id')}; Status: {prop_res.get('status')}."
                })

                if prop_res.get("proposal_id"):
                    state["proposal_id"] = prop_res.get("proposal_id")
                    state["proposal_version"] = prop_res.get("proposal_version", 1)
                    state["pause_for_human_approval"] = True
                    state["workflow_status"] = "PAUSED_FOR_APPROVAL"
                else:
                    state["pause_for_human_approval"] = False
                    state["workflow_status"] = "FAILED"
            else:
                state["pause_for_human_approval"] = False
                state["workflow_status"] = "POLICY_REJECTED"
        else:
            state["policy_validation"] = {"passed": True, "note": "No active proposals generated."}
            state["pause_for_human_approval"] = False
            state["workflow_status"] = "COMPLETED_NO_ACTIONS"

        observation = AgentObservation(
            agent_name="Network Coordinator",
            summary=(
                f"Workflow execution completed with status: {state['workflow_status']}. "
                f"{'Awaiting dual human approval for Proposal ' + str(state.get('proposal_id')) if state.get('pause_for_human_approval') else 'No proposals requiring clinical review.'}"
            ),
            key_findings=[
                f"Workflow status: {state['workflow_status']}.",
                f"Gemini reasoning mode: {state['gemini_status']}.",
                f"MEKO context mode: {state['meko_status']}."
            ],
            uncertainties=gemini_res.get("structured_analysis", {}).get("uncertainty_notes", []),
            data_quality_flags=state.get("data_quality_status", {}).get("flags", [])
        )

        trace = NodeTraceItem(
            node_name="Network Coordinator",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            tool_calls=tool_calls,
            observation=observation.model_dump(),
            status="SUCCESS"
        )

        state.setdefault("agent_observations", {})["orchestrator"] = observation.model_dump()
        state.setdefault("node_trace", []).append(trace.model_dump())

        # Store summary in MEKO
        meko_adapter.store_context(
            summary=(
                f"Workflow {state.get('workflow_id')} completed. Status: {state['workflow_status']}. "
                f"Proposal: {state.get('proposal_id')}."
            ),
            facility_id=state.get("facility_scope"),
            product_id=state.get("product_scope"),
            tags=["workflow_cycle", state["workflow_status"]]
        )

        return state

    # ─────────────────────────────────────────────────────────────
    # BUILD LANGGRAPH STATEGRAPH
    # ─────────────────────────────────────────────────────────────
    builder = StateGraph(AgentGraphState)

    builder.add_node("inventory_monitor", node_inventory_monitor)
    builder.add_node("demand_forecast", node_demand_forecast)
    builder.add_node("expiry_risk", node_expiry_risk)
    builder.add_node("supply_optimization", node_supply_optimization)
    builder.add_node("orchestrator", node_orchestrator)

    builder.set_entry_point("inventory_monitor")
    builder.add_edge("inventory_monitor", "demand_forecast")
    builder.add_edge("demand_forecast", "expiry_risk")
    builder.add_edge("expiry_risk", "supply_optimization")
    builder.add_edge("supply_optimization", "orchestrator")
    builder.add_edge("orchestrator", END)

    return builder.compile(checkpointer=memory_saver or MemorySaver())

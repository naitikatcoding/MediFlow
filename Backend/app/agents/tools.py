"""
Deterministic tool contracts for the MediFlow agent workflow.

Each tool is a narrowly scoped Python function that calls existing backend services.
No tool exposes raw database access to LLM. Every consequential action routes through
authenticated backend service methods.

Tools return structured dicts that are validated by Pydantic before being fed to the
language model or used in workflow decisions.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.services.inventory_service import InventoryService
from app.services.forecast_service import ForecastService
from app.services.risk_service import RiskService
from app.services.matching_service import MatchingService
from app.services.proposal_service import ProposalService
from app.models.proposal import TransferProposal, TransferApproval
from app.models.transfer import Transfer
from app.models.organization import Facility
from app.models.product import Product, Batch
from app.models.consumption import ConsumptionRecord

logger = logging.getLogger("mediflow.agent.tools")


# ──────────────────────────────────────────────
# TOOL 1 – get_facility_inventory
# ──────────────────────────────────────────────
def get_facility_inventory(
    db: Session,
    facility_id: Optional[str] = None,
    product_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Returns usable inventory with data-quality flags.
    Never modifies stock.
    """
    try:
        rows = InventoryService.get_facility_inventory(db, facility_id=facility_id, product_id=product_id)
        # Summarise: flag stale, missing, near-expiry
        stale_flags = []
        missing_data = []
        near_expiry = []
        now = datetime.now(timezone.utc)

        for row in rows:
            freshness = row.get("data_freshness")
            if freshness in ("STALE", "CRITICALLY_STALE"):
                stale_flags.append({
                    "batch_id": row.get("batch_id"),
                    "product_name": row.get("product_name"),
                    "facility_id": row.get("facility_id"),
                    "freshness": freshness
                })
            if row.get("quantity_on_hand") is None:
                missing_data.append(row.get("batch_id"))
            expiry = row.get("expiry_date")
            if expiry:
                try:
                    expiry_dt = datetime.fromisoformat(expiry) if isinstance(expiry, str) else expiry
                    if expiry_dt.tzinfo is None:
                        expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
                    days_left = (expiry_dt - now).days
                    if 0 < days_left <= 60:
                        near_expiry.append({
                            "batch_id": row.get("batch_id"),
                            "product_name": row.get("product_name"),
                            "days_to_expiry": days_left,
                            "quantity_on_hand": row.get("quantity_on_hand", 0)
                        })
                except Exception:
                    pass

        return {
            "tool": "get_facility_inventory",
            "facility_id": facility_id,
            "product_id": product_id,
            "record_count": len(rows),
            "records": rows[:30],  # cap at 30 to avoid bloating LLM context
            "data_quality": {
                "stale_records": stale_flags,
                "missing_quantity_count": len(missing_data),
                "near_expiry_batches": near_expiry
            }
        }
    except Exception as exc:
        logger.exception("get_facility_inventory tool error")
        return {"tool": "get_facility_inventory", "error": str(exc), "record_count": 0, "records": []}


# ──────────────────────────────────────────────
# TOOL 2 – get_consumption_history
# ──────────────────────────────────────────────
def get_consumption_history(
    db: Session,
    facility_id: str,
    product_id: str,
    weeks: int = 12
) -> Dict[str, Any]:
    """
    Returns weekly consumption history for a facility-product pair.
    Used for data-quality validation before forecasting.
    """
    try:
        from datetime import timedelta
        from app.models.consumption import ConsumptionRecord
        cutoff = datetime.now(timezone.utc) - timedelta(weeks=weeks)
        records = (
            db.query(ConsumptionRecord)
            .filter(
                ConsumptionRecord.facility_id == facility_id,
                ConsumptionRecord.product_id == product_id,
                ConsumptionRecord.consumed_at >= cutoff
            )
            .order_by(ConsumptionRecord.consumed_at)
            .all()
        )
        total_qty = sum(r.quantity for r in records)
        missing_weeks = max(0, weeks - len(records))
        return {
            "tool": "get_consumption_history",
            "facility_id": facility_id,
            "product_id": product_id,
            "weeks_requested": weeks,
            "weeks_found": len(records),
            "missing_weeks": missing_weeks,
            "total_consumed": total_qty,
            "has_sufficient_history": len(records) >= 4,
            "records": [
                {
                    "consumed_at": r.consumed_at.isoformat() if r.consumed_at else None,
                    "quantity": r.quantity,
                    "unit": r.unit,
                    "source_system": r.source_system
                }
                for r in records
            ]
        }
    except Exception as exc:
        logger.exception("get_consumption_history tool error")
        return {"tool": "get_consumption_history", "error": str(exc), "has_sufficient_history": False, "records": []}


# ──────────────────────────────────────────────
# TOOL 3 – run_demand_forecast
# ──────────────────────────────────────────────
def run_demand_forecast(
    db: Session,
    facility_id: str,
    product_id: str,
    horizon_days: int = 30
) -> Dict[str, Any]:
    """
    Runs the deterministic weighted moving average forecast.
    Returns structured result including 7d/30d demand, confidence, and warnings.
    Never invents numbers.
    """
    try:
        result = ForecastService.calculate_forecast(db, facility_id, product_id, horizon_days=horizon_days)
        return {
            "tool": "run_demand_forecast",
            "facility_id": facility_id,
            "product_id": product_id,
            "forecast_id": result.get("id"),
            "model_name": result.get("model_name"),
            "daily_average_demand": result.get("daily_average_demand"),
            "demand_7d": result.get("demand_7d"),
            "demand_30d": result.get("demand_30d"),
            "unit": result.get("unit"),
            "confidence_score": result.get("confidence_score"),
            "data_quality_score": result.get("data_quality_score"),
            "warnings": result.get("warnings", []),
            "insufficient_history": result.get("confidence_score", 0) <= 0.1
        }
    except Exception as exc:
        logger.exception("run_demand_forecast tool error")
        return {"tool": "run_demand_forecast", "error": str(exc), "daily_average_demand": 0.0, "insufficient_history": True}


# ──────────────────────────────────────────────
# TOOL 4 – calculate_expiry_risk
# ──────────────────────────────────────────────
def calculate_expiry_risk(
    db: Session,
    facility_id: str,
    product_id: str
) -> Dict[str, Any]:
    """
    Runs FEFO-based expiry depletion simulation.
    Returns projected leftover quantities at expiry, blocked batches excluded.
    """
    try:
        risks = RiskService.evaluate_risks(db, facility_id=facility_id, product_id=product_id)
        expiry_risks = [r for r in risks if r.get("risk_type") == "EXPIRY_RISK"]
        return {
            "tool": "calculate_expiry_risk",
            "facility_id": facility_id,
            "product_id": product_id,
            "expiry_risks_found": len(expiry_risks),
            "risks": expiry_risks[:10],
            "has_critical_expiry": any(r.get("risk_level") == "CRITICAL" for r in expiry_risks)
        }
    except Exception as exc:
        logger.exception("calculate_expiry_risk tool error")
        return {"tool": "calculate_expiry_risk", "error": str(exc), "expiry_risks_found": 0, "risks": []}


# ──────────────────────────────────────────────
# TOOL 5 – calculate_stockout_risk
# ──────────────────────────────────────────────
def calculate_stockout_risk(
    db: Session,
    facility_id: str,
    product_id: str
) -> Dict[str, Any]:
    """
    Runs deterministic days-of-cover stockout risk assessment.
    Returns risk level (CRITICAL/HIGH/MEDIUM/LOW/SAFE) with driving evidence.
    """
    try:
        risks = RiskService.evaluate_risks(db, facility_id=facility_id, product_id=product_id)
        stockout_risks = [r for r in risks if r.get("risk_type") == "STOCKOUT_RISK"]
        return {
            "tool": "calculate_stockout_risk",
            "facility_id": facility_id,
            "product_id": product_id,
            "stockout_risks_found": len(stockout_risks),
            "risks": stockout_risks[:10],
            "has_critical_stockout": any(r.get("risk_level") in ("CRITICAL", "HIGH") for r in stockout_risks)
        }
    except Exception as exc:
        logger.exception("calculate_stockout_risk tool error")
        return {"tool": "calculate_stockout_risk", "error": str(exc), "stockout_risks_found": 0, "risks": []}


# ──────────────────────────────────────────────
# TOOL 6 – find_candidate_facilities
# ──────────────────────────────────────────────
def find_candidate_facilities(
    db: Session,
    product_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Finds source facilities with surplus and destination facilities with unmet need.
    Returns structured candidate pairs with surplus and need quantities.
    """
    try:
        result = MatchingService.find_redistribution_opportunities(db, product_id=product_id)
        return {
            "tool": "find_candidate_facilities",
            "product_id": product_id,
            "accepted_opportunities": len(result.get("accepted_opportunities", [])),
            "rejected_candidates": len(result.get("rejected_candidates", [])),
            "pairs": result.get("accepted_opportunities", [])[:10],
            "rejection_reasons": result.get("rejected_candidates", [])[:10]
        }
    except Exception as exc:
        logger.exception("find_candidate_facilities tool error")
        return {"tool": "find_candidate_facilities", "error": str(exc), "accepted_opportunities": 0, "pairs": []}


# ──────────────────────────────────────────────
# TOOL 7 – calculate_transfer_options
# ──────────────────────────────────────────────
def calculate_transfer_options(
    db: Session,
    source_facility_id: str,
    destination_facility_id: str,
    product_id: str
) -> Dict[str, Any]:
    """
    Calculates eligible transfer quantity for a specific source-destination-product triplet.
    Uses blueprint surplus and need formulas. Does NOT reserve stock.
    """
    try:
        inv_src = InventoryService.get_product_stock_summary(db, source_facility_id, product_id)
        inv_dst = InventoryService.get_product_stock_summary(db, destination_facility_id, product_id)

        fc_src = ForecastService.calculate_forecast(db, source_facility_id, product_id)
        fc_dst = ForecastService.calculate_forecast(db, destination_facility_id, product_id)

        daily_demand_src = fc_src.get("daily_average_demand", 0.0)
        daily_demand_dst = fc_dst.get("daily_average_demand", 0.0)
        safety_stock_src = inv_src.get("safety_stock_qty", 0)
        safety_stock_days_src = max(1, int(safety_stock_src / max(daily_demand_src, 0.01)))

        surplus = RiskService.calculate_candidate_surplus(
            usable_stock=inv_src.get("total_usable", 0),
            daily_demand=daily_demand_src,
            safety_stock_days=safety_stock_days_src,
            horizon_days=30,
            policy_buffer_days=0
        )
        unmet_need = RiskService.calculate_destination_unmet_need(
            target_stock_days=7,
            daily_demand=daily_demand_dst,
            current_usable_stock=inv_dst.get("total_usable", 0),
            confirmed_inbound=inv_dst.get("expected_inbound", 0),
            horizon_days=30
        )
        eligible_qty = RiskService.calculate_eligible_transfer_quantity(
            candidate_surplus=surplus,
            destination_unmet_need=unmet_need,
            batch_eligible_quantity=inv_src.get("total_usable", 0),
            transfer_policy_limit=10000
        )

        # FEFO batch selection from source
        fefo_result = InventoryService.allocate_fefo(
            db, source_facility_id, product_id, eligible_qty
        ) if eligible_qty > 0 else {}
        fefo_batches = fefo_result.get("allocated_batches", []) if isinstance(fefo_result, dict) else []

        return {
            "tool": "calculate_transfer_options",
            "source_facility_id": source_facility_id,
            "destination_facility_id": destination_facility_id,
            "product_id": product_id,
            "source_usable_stock": inv_src.get("total_usable", 0),
            "source_safety_stock": inv_src.get("safety_stock_qty", 0),
            "source_forecast_30d": fc_src.get("demand_30d", 0),
            "candidate_surplus": surplus,
            "destination_usable_stock": inv_dst.get("total_usable", 0),
            "destination_unmet_need": unmet_need,
            "eligible_transfer_quantity": eligible_qty,
            "fefo_batches": fefo_batches[:5],
            "feasible": eligible_qty > 0
        }
    except Exception as exc:
        logger.exception("calculate_transfer_options tool error")
        return {"tool": "calculate_transfer_options", "error": str(exc), "feasible": False, "eligible_transfer_quantity": 0}


# ──────────────────────────────────────────────
# TOOL 8 – validate_transfer_proposal
# ──────────────────────────────────────────────
def validate_transfer_proposal(
    db: Session,
    source_facility_id: str,
    destination_facility_id: str,
    product_id: str,
    quantity: int,
    batches: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Policy validation before proposal creation. Checks:
    - Product not restricted.
    - Source has sufficient usable stock post-reservation.
    - Batches are eligible (not recalled/quarantined/expired).
    - Quantity is positive and non-zero.
    Returns passed=True only when ALL checks pass.
    """
    checks = []
    passed = True

    try:
        # Check quantity > 0
        if quantity <= 0:
            checks.append({"check": "quantity_positive", "passed": False, "reason": f"Quantity {quantity} is not positive."})
            passed = False
        else:
            checks.append({"check": "quantity_positive", "passed": True})

        # Check product policy
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            checks.append({"check": "product_exists", "passed": False, "reason": "Product not found."})
            passed = False
        else:
            checks.append({"check": "product_exists", "passed": True})
            if product.transfer_policy_code == "RESTRICTED_LOCAL_ONLY":
                checks.append({"check": "product_policy", "passed": False, "reason": f"Policy {product.transfer_policy_code} prohibits transfer."})
                passed = False
            else:
                checks.append({"check": "product_policy", "passed": True})

        # Check source stock sufficiency
        inv = InventoryService.get_product_stock_summary(db, source_facility_id, product_id)
        available = inv.get("total_usable", 0) - inv.get("total_reserved", 0)
        if available < quantity:
            checks.append({"check": "source_stock_sufficient", "passed": False, "reason": f"Available {available} < requested {quantity}."})
            passed = False
        else:
            checks.append({"check": "source_stock_sufficient", "passed": True})

        # Check batch eligibility
        for b in batches:
            batch = db.query(Batch).filter(Batch.id == b.get("batch_id")).first()
            if not batch:
                checks.append({"check": f"batch_{b.get('batch_id')}_exists", "passed": False, "reason": "Batch not found."})
                passed = False
            elif batch.quality_status in ("QUARANTINED", "RECALLED", "DAMAGED", "REJECTED", "EXPIRED"):
                checks.append({"check": f"batch_{batch.manufacturer_lot_number}_eligible", "passed": False, "reason": f"Batch quality_status={batch.quality_status}."})
                passed = False
            else:
                checks.append({"check": f"batch_{batch.manufacturer_lot_number}_eligible", "passed": True})

        # Check facilities exist
        src = db.query(Facility).filter(Facility.id == source_facility_id).first()
        dst = db.query(Facility).filter(Facility.id == destination_facility_id).first()
        if not src:
            checks.append({"check": "source_facility_exists", "passed": False, "reason": "Source facility not found."})
            passed = False
        if not dst:
            checks.append({"check": "destination_facility_exists", "passed": False, "reason": "Destination facility not found."})
            passed = False

        return {
            "tool": "validate_transfer_proposal",
            "passed": passed,
            "checks": checks,
            "check_count": len(checks),
            "failure_count": sum(1 for c in checks if not c["passed"])
        }
    except Exception as exc:
        logger.exception("validate_transfer_proposal tool error")
        return {"tool": "validate_transfer_proposal", "error": str(exc), "passed": False, "checks": []}


# ──────────────────────────────────────────────
# TOOL 9 – create_transfer_proposal
# ──────────────────────────────────────────────
def create_transfer_proposal(
    db: Session,
    source_facility_id: str,
    destination_facility_id: str,
    product_id: str,
    quantity: int,
    batches: List[Dict[str, Any]],
    source_rationale: Dict[str, Any],
    destination_rationale: Dict[str, Any],
    workflow_id: Optional[str] = None,
    priority: str = "MEDIUM"
) -> Dict[str, Any]:
    """
    Creates a transfer proposal through the deterministic backend service.
    Requires prior policy validation to have passed.
    Does NOT reserve stock or execute transfer.
    """
    try:
        proposal = ProposalService.create_proposal(
            db=db,
            source_facility_id=source_facility_id,
            destination_facility_id=destination_facility_id,
            product_id=product_id,
            proposed_quantity=quantity,
            batches=batches,
            source_rationale=source_rationale,
            destination_rationale=destination_rationale,
            priority=priority,
            workflow_id=workflow_id
        )
        db.commit()
        return {
            "tool": "create_transfer_proposal",
            "proposal_id": proposal.id,
            "proposal_version": proposal.proposal_version,
            "status": proposal.status,
            "proposed_quantity": proposal.proposed_quantity,
            "priority": proposal.priority,
            "created_at": proposal.created_at.isoformat() if proposal.created_at else None
        }
    except Exception as exc:
        logger.exception("create_transfer_proposal tool error")
        db.rollback()
        return {"tool": "create_transfer_proposal", "error": str(exc), "proposal_id": None}


# ──────────────────────────────────────────────
# TOOL 10 – get_approval_status
# ──────────────────────────────────────────────
def get_approval_status(db: Session, proposal_id: str) -> Dict[str, Any]:
    """
    Returns approval state for a proposal: per-facility decision and version match.
    """
    try:
        proposal = db.query(TransferProposal).filter(TransferProposal.id == proposal_id).first()
        if not proposal:
            return {"tool": "get_approval_status", "found": False, "proposal_id": proposal_id}

        approvals = db.query(TransferApproval).filter(TransferApproval.proposal_id == proposal_id).all()
        approval_map = {}
        for a in approvals:
            key = a.facility_id
            if key not in approval_map or a.decided_at > approval_map[key]["decided_at"]:
                approval_map[key] = {
                    "facility_id": a.facility_id,
                    "decision": a.decision,
                    "proposal_version": a.proposal_version,
                    "decided_at": a.decided_at,
                    "version_matches": a.proposal_version == proposal.proposal_version
                }

        src_approval = approval_map.get(proposal.source_facility_id)
        dst_approval = approval_map.get(proposal.destination_facility_id)

        fully_approved = (
            src_approval and src_approval["decision"] == "APPROVED" and src_approval["version_matches"] and
            dst_approval and dst_approval["decision"] == "APPROVED" and dst_approval["version_matches"]
        )

        return {
            "tool": "get_approval_status",
            "proposal_id": proposal_id,
            "proposal_version": proposal.proposal_version,
            "proposal_status": proposal.status,
            "source_approval": src_approval,
            "destination_approval": dst_approval,
            "fully_approved": fully_approved,
            "any_rejected": any(a["decision"] == "REJECTED" for a in approval_map.values())
        }
    except Exception as exc:
        logger.exception("get_approval_status tool error")
        return {"tool": "get_approval_status", "error": str(exc), "fully_approved": False}


# ──────────────────────────────────────────────
# TOOL 11 – get_transfer_status
# ──────────────────────────────────────────────
def get_transfer_status(db: Session, proposal_id: str) -> Dict[str, Any]:
    """
    Returns transfer execution status for a proposal.
    """
    try:
        transfer = db.query(Transfer).filter(Transfer.proposal_id == proposal_id).first()
        if not transfer:
            return {"tool": "get_transfer_status", "found": False, "proposal_id": proposal_id}
        return {
            "tool": "get_transfer_status",
            "transfer_id": transfer.id,
            "proposal_id": proposal_id,
            "status": transfer.status,
            "dispatched_at": transfer.dispatched_at.isoformat() if transfer.dispatched_at else None,
            "received_at": transfer.received_at.isoformat() if transfer.received_at else None
        }
    except Exception as exc:
        logger.exception("get_transfer_status tool error")
        return {"tool": "get_transfer_status", "error": str(exc), "found": False}

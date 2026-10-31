import logging
from datetime import datetime, timezone, timedelta, date
from typing import List, Dict, Any, Optional
from uuid import NAMESPACE_URL, uuid5
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.intelligence import RiskAssessment, ForecastRun
from app.models.organization import Facility
from app.models.product import Product, Batch
from app.models.consumption import PurchaseOrder, PurchaseOrderLine
from app.services.inventory_service import InventoryService
from app.services.forecast_service import ForecastService

logger = logging.getLogger("mediflow.risk")


def _risk_id(
    facility_id: str,
    product_id: str,
    risk_type: str,
    subject_id: str = "",
) -> str:
    """Generates an opaque, deterministic UUID for a risk assessment."""
    return str(uuid5(
        NAMESPACE_URL,
        f"mediflow-risk:{facility_id}:{product_id}:{risk_type}:{subject_id}",
    ))


class RiskService:
    """
    Deterministic clinical supply risk and expiry detection engine.
    Calculates stockout risks, safety-stock violations, and FEFO expiry leftovers
    using transparent domain mathematics and verified parameters.
    Never relies on non-deterministic LLM-generated risk scores.
    """

    # Configurable domain thresholds (inventory planning labels, not clinical severity)
    DEFAULT_LEAD_TIME_DAYS = 4
    DEFAULT_SAFETY_STOCK_DAYS = 7
    DEFAULT_PLANNING_HORIZON_DAYS = 30

    @staticmethod
    def calculate_days_of_cover(usable_stock: int, daily_demand: float) -> float:
        """
        Calculates how many days current usable stock will last at forecast consumption rate.
        """
        if daily_demand <= 0.0:
            return 999.0 if usable_stock > 0 else 0.0
        return round(usable_stock / daily_demand, 1)

    @staticmethod
    def evaluate_stockout_risk(
        usable_stock: int,
        daily_demand: float,
        lead_time_days: int = DEFAULT_LEAD_TIME_DAYS,
        safety_stock_days: int = DEFAULT_SAFETY_STOCK_DAYS,
        confirmed_inbound: int = 0,
        horizon_days: int = DEFAULT_PLANNING_HORIZON_DAYS,
        data_freshness_days: int = 0,
        cv: float = 0.2
    ) -> Dict[str, Any]:
        """
        Evaluates stockout risk level and deficit quantity deterministically:
        - Critical: projected stock runs out before replenishment arrives (cover <= lead time)
        - High: projected stock breaches safety stock within lead-time window (cover <= safety stock)
        - Medium: projected stock breaches buffer within planning horizon (cover <= safety stock + 7)
        - Low: no current buffer breach within immediate planning horizon
        - Safe: ample stock cover exceeding horizon
        """
        days_of_cover = RiskService.calculate_days_of_cover(usable_stock, daily_demand)
        safety_stock_required = int(round(daily_demand * safety_stock_days))
        replenishment_buffer_required = int(round(daily_demand * lead_time_days))
        target_buffer = safety_stock_required + replenishment_buffer_required

        today = datetime.now(timezone.utc).date()
        projected_stockout_date = None

        if days_of_cover <= lead_time_days:
            level = "CRITICAL"
            score = 95.0
            projected_days = max(0, int(days_of_cover))
            projected_stockout_date = (today + timedelta(days=projected_days)).isoformat()
        elif days_of_cover <= safety_stock_days:
            level = "HIGH"
            score = 75.0
            projected_days = max(0, int(days_of_cover))
            projected_stockout_date = (today + timedelta(days=projected_days)).isoformat()
        elif days_of_cover <= (safety_stock_days + 7):
            level = "MEDIUM"
            score = 45.0
            projected_stockout_date = (today + timedelta(days=int(days_of_cover))).isoformat()
        elif days_of_cover <= horizon_days:
            level = "LOW"
            score = 15.0
        else:
            level = "SAFE"
            score = 0.0

        deficit_qty = max(0, target_buffer - usable_stock - confirmed_inbound)

        return {
            "risk_level": level,
            "score": score,
            "days_of_cover": days_of_cover,
            "projected_stockout_date": projected_stockout_date,
            "deficit_quantity": deficit_qty,
            "safety_stock_required": safety_stock_required,
            "replenishment_buffer_required": replenishment_buffer_required,
            "target_buffer": target_buffer,
            "lead_time_days": lead_time_days,
            "safety_stock_days": safety_stock_days
        }

    @staticmethod
    def simulate_fefo_expiry_depletion(
        batches: List[Dict[str, Any]],
        daily_demand: float,
        planning_horizon_days: int = 90
    ) -> List[Dict[str, Any]]:
        """
        Simulates batch depletion under FEFO (First-Expired, First-Out) using forecast demand.
        Calculates projected leftover unconsumed quantity at each batch's expiry date.
        Excludes blocked batches from redistribution calculations.
        """
        expiry_risks: List[Dict[str, Any]] = []

        # Separate already expired, blocked, and eligible batches
        # Eligible batches must have usable stock and be RELEASED
        eligible_batches = []
        for b in batches:
            usable = b.get("usable_quantity", 0)
            status = b.get("quality_status", "RELEASED")
            days_to_exp = b.get("days_to_expiry", 0)

            if days_to_exp < 0 and usable > 0:
                # Already expired batch
                expiry_risks.append({
                    "batch_id": b.get("batch_id"),
                    "lot_number": b.get("manufacturer_lot_number"),
                    "expiry_date": str(b.get("expiry_date")),
                    "days_to_expiry": days_to_exp,
                    "usable_quantity": usable,
                    "unconsumed_quantity": usable,
                    "risk_level": "CRITICAL",
                    "score": 100.0,
                    "is_already_expired": True,
                    "reason": f"Batch {b.get('manufacturer_lot_number')} is past expiry date ({b.get('expiry_date')}). Quarantined for disposal."
                })
            elif status in ("RELEASED", "ACTIVE") and usable > 0:
                eligible_batches.append(b)

        # Sort eligible batches in FEFO order (earliest expiry first)
        eligible_batches.sort(key=lambda x: x.get("expiry_date") or date.max)

        # Simulate depletion chronologically
        prior_batches_consumed = 0

        for b in eligible_batches:
            b_usable = b.get("usable_quantity", 0)
            days_to_exp = b.get("days_to_expiry", 0)
            lot_num = b.get("manufacturer_lot_number")
            exp_date_str = str(b.get("expiry_date"))

            # Total demand that will occur from Day 0 until this batch expires
            cumulative_demand_at_exp = daily_demand * max(0, days_to_exp)

            # Demand available to absorb this batch (after prior batches are absorbed)
            available_demand_for_batch = max(0.0, cumulative_demand_at_exp - prior_batches_consumed)

            # Leftover units that will expire before local consumption can absorb them
            leftover = max(0, b_usable - int(available_demand_for_batch))

            # Update prior consumed
            absorbed_qty = min(b_usable, int(available_demand_for_batch))
            prior_batches_consumed += b_usable

            if leftover > 0 and days_to_exp <= planning_horizon_days:
                if days_to_exp <= 30:
                    level = "CRITICAL"
                    score = 90.0
                elif days_to_exp <= 60:
                    level = "HIGH"
                    score = 75.0
                else:
                    level = "MEDIUM"
                    score = 50.0

                expiry_risks.append({
                    "batch_id": b.get("batch_id"),
                    "lot_number": lot_num,
                    "expiry_date": exp_date_str,
                    "days_to_expiry": days_to_exp,
                    "usable_quantity": b_usable,
                    "unconsumed_quantity": leftover,
                    "risk_level": level,
                    "score": score,
                    "is_already_expired": False,
                    "reason": f"Projected {leftover} units of batch {lot_num} will expire in {days_to_exp} days before local consumption can absorb them."
                })

        return expiry_risks

    @staticmethod
    def calculate_candidate_surplus(
        usable_stock: int,
        daily_demand: float,
        safety_stock_days: int = DEFAULT_SAFETY_STOCK_DAYS,
        horizon_days: int = DEFAULT_PLANNING_HORIZON_DAYS,
        policy_buffer_days: int = 0
    ) -> int:
        """
        Blueprint surplus formula:
        candidate_surplus = max(0, eligible_usable_stock - projected_local_need - safety_stock - policy_buffer)

        Note: Reservations are NOT subtracted twice because usable_stock already excludes them.
        """
        projected_local_need = int(round(daily_demand * horizon_days))
        safety_stock = int(round(daily_demand * safety_stock_days))
        policy_buffer = int(round(daily_demand * policy_buffer_days))

        protected_quantity = projected_local_need + safety_stock + policy_buffer
        return max(0, usable_stock - protected_quantity)

    @staticmethod
    def calculate_destination_unmet_need(
        target_stock_days: int,
        daily_demand: float,
        current_usable_stock: int,
        confirmed_inbound: int = 0,
        horizon_days: int = DEFAULT_PLANNING_HORIZON_DAYS
    ) -> int:
        """
        Blueprint destination need formula:
        destination_unmet_need = max(0, target_stock_position - projected_stock_position_after_confirmed_inbound)
        """
        target_stock = int(round(daily_demand * target_stock_days))
        projected_stock_after_inbound = current_usable_stock + confirmed_inbound - int(round(daily_demand * horizon_days))
        return max(0, target_stock - projected_stock_after_inbound)

    @staticmethod
    def calculate_eligible_transfer_quantity(
        candidate_surplus: int,
        destination_unmet_need: int,
        batch_eligible_quantity: int,
        transfer_policy_limit: Optional[int] = None
    ) -> int:
        """
        Blueprint eligible transfer formula:
        eligible_transfer_quantity = min(candidate_surplus, destination_unmet_need, batch_eligible_quantity, transfer_policy_limit)
        """
        limit = transfer_policy_limit if transfer_policy_limit is not None else 999999
        return max(0, min(candidate_surplus, destination_unmet_need, batch_eligible_quantity, limit))

    @staticmethod
    def evaluate_risks(
        db: Session,
        facility_id: Optional[str] = None,
        product_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Master risk evaluation method. Evaluates stockout risks, expiry risks,
        and surplus availability across facilities and products.
        Persists evaluated records in the database.
        """
        fac_query = db.query(Facility).filter(Facility.status == "ACTIVE")
        if facility_id:
            fac_query = fac_query.filter(Facility.id == facility_id)
        facilities = fac_query.all()

        prod_query = db.query(Product).filter(Product.status == "ACTIVE")
        if product_id:
            prod_query = prod_query.filter(Product.id == product_id)
        products = prod_query.all()

        now = datetime.now(timezone.utc)
        today = now.date()
        assessments: List[Dict[str, Any]] = []

        for fac in facilities:
            for prod in products:
                # 1. Fetch current inventory
                inv_summary = InventoryService.get_product_stock_summary(db, fac.id, prod.id)
                usable_stock = inv_summary.get("total_usable", 0)
                batches = inv_summary.get("batches", [])

                # 2. Fetch forecast
                fc = ForecastService.calculate_forecast(db, fac.id, prod.id, horizon_days=RiskService.DEFAULT_PLANNING_HORIZON_DAYS)
                daily_demand = fc["daily_average_demand"]

                # Inactive medicine (no stock and no consumption)
                if daily_demand <= 0.05 and usable_stock == 0:
                    continue

                # 3. Confirmed inbound purchase orders
                pos = db.query(PurchaseOrder).join(PurchaseOrderLine).filter(
                    PurchaseOrder.facility_id == fac.id,
                    PurchaseOrder.status.in_(["CONFIRMED", "IN_TRANSIT", "PLACED"]),
                    PurchaseOrderLine.product_id == prod.id
                ).all()

                confirmed_inbound = 0
                for po in pos:
                    for line in po.lines:
                        if line.product_id == prod.id:
                            confirmed_inbound += max(0, line.quantity_ordered - line.quantity_received)

                # --- A. Stockout Risk Evaluation ---
                stockout_eval = RiskService.evaluate_stockout_risk(
                    usable_stock=usable_stock,
                    daily_demand=daily_demand,
                    lead_time_days=RiskService.DEFAULT_LEAD_TIME_DAYS,
                    safety_stock_days=RiskService.DEFAULT_SAFETY_STOCK_DAYS,
                    confirmed_inbound=confirmed_inbound,
                    horizon_days=RiskService.DEFAULT_PLANNING_HORIZON_DAYS
                )

                days_of_cover = stockout_eval["days_of_cover"]
                stockout_level = stockout_eval["risk_level"]

                if stockout_level in ("CRITICAL", "HIGH", "MEDIUM"):
                    deficit_qty = stockout_eval["deficit_quantity"]
                    risk_record = {
                        "id": _risk_id(fac.id, prod.id, "STOCKOUT_RISK"),
                        "facility_id": fac.id,
                        "facility_name": fac.name,
                        "product_id": prod.id,
                        "product_name": prod.name,
                        "risk_type": "STOCKOUT_RISK",
                        "risk_level": stockout_level,
                        "score": stockout_eval["score"],
                        "days_of_cover": days_of_cover,
                        "projected_stockout_date": stockout_eval["projected_stockout_date"],
                        "at_risk_quantity": deficit_qty,
                        "explanation": {
                            "usable_stock": usable_stock,
                            "daily_demand": daily_demand,
                            "days_of_cover": days_of_cover,
                            "safety_stock_required": stockout_eval["safety_stock_required"],
                            "lead_time_days": stockout_eval["lead_time_days"],
                            "confirmed_inbound": confirmed_inbound,
                            "confidence_score": fc["confidence_score"],
                            "warnings": fc["warnings"],
                            "summary": f"Stock will deplete in {days_of_cover} days at {daily_demand} units/day. Minimum buffer requires {stockout_eval['safety_stock_required']} units."
                        },
                        "created_at": now
                    }
                    assessments.append(risk_record)
                    RiskService._persist_risk_record(db, risk_record, fc.get("id"))

                # --- B. Expiry Risk Evaluation (FEFO Depletion) ---
                expiry_items = RiskService.simulate_fefo_expiry_depletion(
                    batches=batches,
                    daily_demand=daily_demand,
                    planning_horizon_days=90
                )

                for exp_item in expiry_items:
                    exp_risk_record = {
                        "id": _risk_id(fac.id, prod.id, "EXPIRY_RISK", exp_item["batch_id"]),
                        "facility_id": fac.id,
                        "facility_name": fac.name,
                        "product_id": prod.id,
                        "product_name": prod.name,
                        "risk_type": "EXPIRY_RISK",
                        "risk_level": exp_item["risk_level"],
                        "score": exp_item["score"],
                        "days_of_cover": days_of_cover,
                        "at_risk_quantity": exp_item["unconsumed_quantity"],
                        "explanation": {
                            "batch_id": exp_item["batch_id"],
                            "lot_number": exp_item["lot_number"],
                            "expiry_date": exp_item["expiry_date"],
                            "days_until_expiry": exp_item["days_to_expiry"],
                            "unconsumed_quantity": exp_item["unconsumed_quantity"],
                            "is_already_expired": exp_item["is_already_expired"],
                            "summary": exp_item["reason"]
                        },
                        "created_at": now
                    }
                    assessments.append(exp_risk_record)
                    RiskService._persist_risk_record(db, exp_risk_record, fc.get("id"))

                # --- C. Surplus Availability Evaluation ---
                surplus_qty = RiskService.calculate_candidate_surplus(
                    usable_stock=usable_stock,
                    daily_demand=daily_demand,
                    safety_stock_days=RiskService.DEFAULT_SAFETY_STOCK_DAYS,
                    horizon_days=RiskService.DEFAULT_PLANNING_HORIZON_DAYS
                )

                if surplus_qty >= 10:
                    surplus_record = {
                        "id": _risk_id(fac.id, prod.id, "SURPLUS_AVAILABLE"),
                        "facility_id": fac.id,
                        "facility_name": fac.name,
                        "product_id": prod.id,
                        "product_name": prod.name,
                        "risk_type": "SURPLUS_AVAILABLE",
                        "risk_level": "SAFE",
                        "score": 0.0,
                        "days_of_cover": days_of_cover,
                        "at_risk_quantity": surplus_qty,
                        "explanation": {
                            "usable_stock": usable_stock,
                            "protected_local_qty": usable_stock - surplus_qty,
                            "transferable_surplus": surplus_qty,
                            "daily_demand": daily_demand,
                            "summary": f"{surplus_qty} units available as eligible surplus beyond 37 days of cover."
                        },
                        "created_at": now
                    }
                    assessments.append(surplus_record)
                    RiskService._persist_risk_record(db, surplus_record, fc.get("id"))

        db.flush()
        return assessments

    @staticmethod
    def _persist_risk_record(db: Session, record: Dict[str, Any], forecast_run_id: Optional[str] = None):
        """Persists or updates the RiskAssessment row in database."""
        existing = db.query(RiskAssessment).filter(RiskAssessment.id == record["id"]).first()
        if existing:
            existing.risk_level = record["risk_level"]
            existing.score = record["score"]
            existing.explanation = record["explanation"]
            existing.forecast_run_id = forecast_run_id
        else:
            db.add(RiskAssessment(
                id=record["id"],
                facility_id=record["facility_id"],
                product_id=record["product_id"],
                risk_type=record["risk_type"],
                risk_level=record["risk_level"],
                score=record["score"],
                explanation=record["explanation"],
                forecast_run_id=forecast_run_id,
                created_at=record["created_at"]
            ))

    @staticmethod
    def get_risk_by_id(db: Session, risk_id: str) -> Optional[Dict[str, Any]]:
        """Fetches a single risk assessment with full evidence detail."""
        all_risks = RiskService.evaluate_risks(db)
        for r in all_risks:
            if r["id"] == risk_id:
                return r

        # Fallback to DB record
        db_record = db.query(RiskAssessment).filter(RiskAssessment.id == risk_id).first()
        if not db_record:
            return None

        fac = db.query(Facility).filter(Facility.id == db_record.facility_id).first()
        prod = db.query(Product).filter(Product.id == db_record.product_id).first()
        return {
            "id": db_record.id,
            "facility_id": db_record.facility_id,
            "facility_name": fac.name if fac else None,
            "product_id": db_record.product_id,
            "product_name": prod.name if prod else None,
            "risk_type": db_record.risk_type,
            "risk_level": db_record.risk_level,
            "score": db_record.score,
            "days_of_cover": db_record.explanation.get("days_of_cover"),
            "projected_stockout_date": db_record.explanation.get("projected_stockout_date"),
            "at_risk_quantity": db_record.explanation.get("unconsumed_quantity") or db_record.explanation.get("deficit_quantity"),
            "explanation": db_record.explanation,
            "created_at": db_record.created_at
        }

    @staticmethod
    def get_risks_summary(db: Session) -> Dict[str, Any]:
        """Provides high-level counts and facility breakdowns for stockout and expiry risks."""
        risks = RiskService.evaluate_risks(db)

        stockout_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "safe": 0, "total": 0}
        expiry_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "safe": 0, "total": 0}
        surplus_count = 0
        critical_alerts = 0
        by_facility: Dict[str, Dict[str, int]] = {}

        for r in risks:
            rtype = r["risk_type"]
            rlevel = r["risk_level"].lower()
            fac_name = r.get("facility_name", r["facility_id"])

            if fac_name not in by_facility:
                by_facility[fac_name] = {"stockout": 0, "expiry": 0, "surplus": 0}

            if rtype == "STOCKOUT_RISK":
                stockout_counts["total"] += 1
                if rlevel in stockout_counts:
                    stockout_counts[rlevel] += 1
                if rlevel == "critical":
                    critical_alerts += 1
                by_facility[fac_name]["stockout"] += 1
            elif rtype == "EXPIRY_RISK":
                expiry_counts["total"] += 1
                if rlevel in expiry_counts:
                    expiry_counts[rlevel] += 1
                if rlevel == "critical":
                    critical_alerts += 1
                by_facility[fac_name]["expiry"] += 1
            elif rtype == "SURPLUS_AVAILABLE":
                surplus_count += 1
                by_facility[fac_name]["surplus"] += 1

        return {
            "total_risks": len(risks),
            "stockout_risks": stockout_counts,
            "expiry_risks": expiry_counts,
            "surplus_available": surplus_count,
            "critical_alerts": critical_alerts,
            "by_facility": by_facility
        }

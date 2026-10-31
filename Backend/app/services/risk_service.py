from datetime import datetime, timezone, timedelta, date
from typing import List, Dict, Any, Optional
from uuid import NAMESPACE_URL, uuid5
from sqlalchemy.orm import Session
from app.models.intelligence import RiskAssessment
from app.models.organization import Facility
from app.models.product import Product, Batch
from app.services.inventory_service import InventoryService
from app.services.forecast_service import ForecastService


def _risk_id(
    facility_id: str,
    product_id: str,
    risk_type: str,
    subject_id: str = "",
) -> str:
    return str(uuid5(
        NAMESPACE_URL,
        f"mediflow-risk:{facility_id}:{product_id}:{risk_type}:{subject_id}",
    ))


class RiskService:
    @staticmethod
    def evaluate_risks(
        db: Session,
        facility_id: Optional[str] = None,
        product_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Evaluates stockout risks, expiry risks, and surplus availability
        across facilities and products using deterministic domain math.
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
        assessments = []

        # Standard policy parameters (can be configured per facility)
        LEAD_TIME_DAYS = 4
        SAFETY_STOCK_DAYS = 7
        PLANNING_HORIZON_DAYS = 30

        for fac in facilities:
            for prod in products:
                # 1. Fetch current inventory
                inv_summary = InventoryService.get_product_stock_summary(db, fac.id, prod.id)
                usable_stock = inv_summary["total_usable"]
                batches = inv_summary["batches"]

                # 2. Fetch forecast
                fc = ForecastService.calculate_forecast(db, fac.id, prod.id, horizon_days=PLANNING_HORIZON_DAYS)
                daily_demand = fc["daily_average_demand"]

                if daily_demand <= 0.05 and usable_stock == 0:
                    continue  # Inactive medicine at this facility

                days_of_cover = round(usable_stock / daily_demand, 1) if daily_demand > 0 else 999.0
                safety_stock_required = int(daily_demand * SAFETY_STOCK_DAYS)
                horizon_demand = int(daily_demand * PLANNING_HORIZON_DAYS)

                # --- Stockout Risk Evaluation ---
                stockout_level = "SAFE"
                stockout_score = 0.0
                projected_stockout_date = None

                if days_of_cover <= LEAD_TIME_DAYS:
                    stockout_level = "CRITICAL"
                    stockout_score = 95.0
                    projected_stockout_date = (today + timedelta(days=max(0, int(days_of_cover)))).isoformat()
                elif days_of_cover <= SAFETY_STOCK_DAYS:
                    stockout_level = "HIGH"
                    stockout_score = 75.0
                    projected_stockout_date = (today + timedelta(days=int(days_of_cover))).isoformat()
                elif days_of_cover <= (SAFETY_STOCK_DAYS + 7):
                    stockout_level = "MEDIUM"
                    stockout_score = 45.0
                else:
                    stockout_level = "LOW"
                    stockout_score = 10.0

                if stockout_level in ("CRITICAL", "HIGH", "MEDIUM"):
                    deficit_qty = max(0, safety_stock_required + int(daily_demand * LEAD_TIME_DAYS) - usable_stock)
                    assessments.append({
                        "id": _risk_id(fac.id, prod.id, "STOCKOUT_RISK"),
                        "facility_id": fac.id,
                        "facility_name": fac.name,
                        "product_id": prod.id,
                        "product_name": prod.name,
                        "risk_type": "STOCKOUT_RISK",
                        "risk_level": stockout_level,
                        "score": stockout_score,
                        "days_of_cover": days_of_cover,
                        "projected_stockout_date": projected_stockout_date,
                        "at_risk_quantity": deficit_qty,
                        "explanation": {
                            "usable_stock": usable_stock,
                            "daily_demand": daily_demand,
                            "days_of_cover": days_of_cover,
                            "safety_stock_required": safety_stock_required,
                            "lead_time_days": LEAD_TIME_DAYS,
                            "confidence_score": fc["confidence_score"],
                            "warnings": fc["warnings"],
                            "summary": f"Stock will deplete in {days_of_cover} days at {daily_demand} units/day. Minimum buffer requires {safety_stock_required} units."
                        },
                        "created_at": now
                    })

                # --- Expiry Risk Evaluation (FEFO-based) ---
                accumulated_consumption = 0
                for b in batches:
                    b_usable = b["usable_quantity"]
                    if b_usable <= 0:
                        continue
                    days_until_exp = b["days_to_expiry"]
                    if days_until_exp < 0:
                        # Already expired
                        assessments.append({
                            "id": _risk_id(fac.id, prod.id, "EXPIRY_RISK", b["batch_id"]),
                            "facility_id": fac.id,
                            "facility_name": fac.name,
                            "product_id": prod.id,
                            "product_name": prod.name,
                            "risk_type": "EXPIRY_RISK",
                            "risk_level": "CRITICAL",
                            "score": 100.0,
                            "days_of_cover": days_of_cover,
                            "at_risk_quantity": b_usable,
                            "explanation": {
                                "lot_number": b["manufacturer_lot_number"],
                                "expiry_date": str(b["expiry_date"]),
                                "days_until_expiry": days_until_exp,
                                "unconsumed_quantity": b_usable,
                                "summary": f"Batch {b['manufacturer_lot_number']} is already past expiry ({b['expiry_date']}). Must be quarantined immediately."
                            },
                            "created_at": now
                        })
                    else:
                        # Check projected consumption before expiry
                        projected_cons_before_exp = int(daily_demand * days_until_exp)
                        potential_surplus_before_exp = max(0, b_usable - max(0, projected_cons_before_exp - accumulated_consumption))
                        accumulated_consumption += b_usable

                        if potential_surplus_before_exp > 0 and days_until_exp <= 90:
                            # Leftover stock will expire before local need
                            exp_level = "HIGH" if days_until_exp <= 45 else "MEDIUM"
                            assessments.append({
                                "id": _risk_id(fac.id, prod.id, "EXPIRY_RISK", b["batch_id"]),
                                "facility_id": fac.id,
                                "facility_name": fac.name,
                                "product_id": prod.id,
                                "product_name": prod.name,
                                "risk_type": "EXPIRY_RISK",
                                "risk_level": exp_level,
                                "score": 80.0 if exp_level == "HIGH" else 50.0,
                                "days_of_cover": days_of_cover,
                                "at_risk_quantity": potential_surplus_before_exp,
                                "explanation": {
                                    "batch_id": b["batch_id"],
                                    "lot_number": b["manufacturer_lot_number"],
                                    "expiry_date": str(b["expiry_date"]),
                                    "days_until_expiry": days_until_exp,
                                    "unconsumed_quantity": potential_surplus_before_exp,
                                    "summary": f"Projected {potential_surplus_before_exp} units of batch {b['manufacturer_lot_number']} will expire before local consumption can absorb them."
                                },
                                "created_at": now
                            })

                # --- Surplus Evaluation ---
                if days_of_cover > (PLANNING_HORIZON_DAYS + SAFETY_STOCK_DAYS):
                    # Local requirement for horizon + safety buffer
                    protected_qty = int(daily_demand * (PLANNING_HORIZON_DAYS + SAFETY_STOCK_DAYS))
                    transferable_surplus = max(0, usable_stock - protected_qty)
                    if transferable_surplus >= 10:
                        assessments.append({
                            "id": _risk_id(fac.id, prod.id, "SURPLUS_AVAILABLE"),
                            "facility_id": fac.id,
                            "facility_name": fac.name,
                            "product_id": prod.id,
                            "product_name": prod.name,
                            "risk_type": "SURPLUS_AVAILABLE",
                            "risk_level": "SAFE",
                            "score": 0.0,
                            "days_of_cover": days_of_cover,
                            "at_risk_quantity": transferable_surplus,
                            "explanation": {
                                "usable_stock": usable_stock,
                                "protected_local_qty": protected_qty,
                                "transferable_surplus": transferable_surplus,
                                "daily_demand": daily_demand,
                                "summary": f"{transferable_surplus} units available as eligible surplus beyond 37 days of cover."
                            },
                            "created_at": now
                        })

        return assessments

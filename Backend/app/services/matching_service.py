from datetime import datetime, timezone, timedelta, date
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models.organization import Facility
from app.models.product import Product, Batch
from app.services.inventory_service import InventoryService
from app.services.forecast_service import ForecastService
from app.services.risk_service import RiskService


class MatchingService:
    @staticmethod
    def find_redistribution_opportunities(
        db: Session,
        product_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Deterministic matching engine: evaluates candidate source facilities with surplus
        against destination facilities with shortages, checking all physical and policy constraints.
        Returns accepted matches AND structured reasons for rejected candidate pairs.
        """
        now = datetime.now(timezone.utc)
        today = now.date()
        SAFETY_STOCK_DAYS = 7
        PLANNING_HORIZON_DAYS = 30
        TRANSIT_BUFFER_DAYS = 2

        products = db.query(Product).filter(Product.status == "ACTIVE")
        if product_id:
            products = products.filter(Product.id == product_id)
        all_products = products.all()

        facilities = {f.id: f for f in db.query(Facility).filter(Facility.status == "ACTIVE").all()}

        accepted_opportunities = []
        rejected_candidates = []

        for prod in all_products:
            # Check policy code
            if prod.transfer_policy_code == "RESTRICTED_LOCAL_ONLY":
                rejected_candidates.append({
                    "product_id": prod.id,
                    "product_name": prod.name,
                    "source_facility_id": "ALL",
                    "destination_facility_id": "ALL",
                    "rejected_reason": "PRODUCT_POLICY_RESTRICTED",
                    "explanation": f"Product policy '{prod.transfer_policy_code}' strictly prohibits inter-facility transfer."
                })
                continue

            # Identify destinations in need
            destinations_in_need = []
            for fac_id, fac in facilities.items():
                inv = InventoryService.get_product_stock_summary(db, fac_id, prod.id)
                fc = ForecastService.calculate_forecast(db, fac_id, prod.id, horizon_days=PLANNING_HORIZON_DAYS)
                daily_d = fc["daily_average_demand"]
                if daily_d <= 0.05:
                    continue

                days_of_cover = inv["total_usable"] / daily_d
                target_stock = int(daily_d * (PLANNING_HORIZON_DAYS + SAFETY_STOCK_DAYS))
                unmet_need = max(0, target_stock - inv["total_usable"])

                if days_of_cover <= 14 and unmet_need > 0:
                    destinations_in_need.append({
                        "facility": fac,
                        "daily_demand": daily_d,
                        "days_of_cover": days_of_cover,
                        "unmet_need": unmet_need,
                        "current_usable": inv["total_usable"]
                    })

            if not destinations_in_need:
                continue

            # Identify sources with surplus
            sources_with_surplus = []
            for fac_id, fac in facilities.items():
                inv = InventoryService.get_product_stock_summary(db, fac_id, prod.id)
                fc = ForecastService.calculate_forecast(db, fac_id, prod.id, horizon_days=PLANNING_HORIZON_DAYS)
                daily_d = fc["daily_average_demand"]
                
                # Minimum reserved buffer: local demand for horizon + safety stock
                protected_qty = int(daily_d * (PLANNING_HORIZON_DAYS + SAFETY_STOCK_DAYS))
                surplus_qty = max(0, inv["total_usable"] - protected_qty)

                if surplus_qty > 0 and inv["batches"]:
                    sources_with_surplus.append({
                        "facility": fac,
                        "daily_demand": daily_d,
                        "surplus_qty": surplus_qty,
                        "batches": inv["batches"]
                    })

            # Match candidates and validate constraints
            for dest in destinations_in_need:
                dest_fac = dest["facility"]
                dest_caps = dest_fac.storage_capabilities or {}

                for src in sources_with_surplus:
                    src_fac = src["facility"]
                    if src_fac.id == dest_fac.id:
                        continue  # Cannot transfer to self

                    # Constraint 1: Storage / Cold Chain Compatibility
                    if prod.storage_requirements == "COLD_CHAIN_2_8C":
                        if not dest_caps.get("cold_chain", False):
                            rejected_candidates.append({
                                "product_id": prod.id,
                                "product_name": prod.name,
                                "source_facility_id": src_fac.id,
                                "source_facility_name": src_fac.name,
                                "destination_facility_id": dest_fac.id,
                                "destination_facility_name": dest_fac.name,
                                "rejected_reason": "STORAGE_INCOMPATIBILITY",
                                "explanation": f"Destination '{dest_fac.name}' lacks certified 2-8°C cold chain storage for {prod.name}."
                            })
                            continue

                    # Constraint 2: Batch Eligibility and Shelf Life
                    # Select batches using FEFO
                    feasible_batches = []
                    feasible_qty_accum = 0

                    for b in src["batches"]:
                        usable_in_batch = b["usable_quantity"]
                        if usable_in_batch <= 0:
                            continue

                        days_to_exp = b["days_to_expiry"]
                        # Minimum required shelf life: transit + destination consumption time
                        min_required_shelf_life = TRANSIT_BUFFER_DAYS + 14
                        if days_to_exp < min_required_shelf_life:
                            rejected_candidates.append({
                                "product_id": prod.id,
                                "product_name": prod.name,
                                "source_facility_id": src_fac.id,
                                "source_facility_name": src_fac.name,
                                "destination_facility_id": dest_fac.id,
                                "destination_facility_name": dest_fac.name,
                                "batch_lot": b["manufacturer_lot_number"],
                                "rejected_reason": "INSUFFICIENT_REMAINING_SHELF_LIFE",
                                "explanation": f"Batch {b['manufacturer_lot_number']} expires in {days_to_exp} days, below minimum viable shelf life of {min_required_shelf_life} days."
                            })
                            continue

                        # Feasible batch portion
                        take_qty = min(usable_in_batch, src["surplus_qty"] - feasible_qty_accum, dest["unmet_need"] - feasible_qty_accum)
                        if take_qty > 0:
                            feasible_batches.append({
                                "batch_id": b["batch_id"],
                                "manufacturer_lot_number": b["manufacturer_lot_number"],
                                "expiry_date": b["expiry_date"],
                                "days_to_expiry": days_to_exp,
                                "quantity": take_qty,
                                "unit": b["unit"]
                            })
                            feasible_qty_accum += take_qty

                        if feasible_qty_accum >= dest["unmet_need"]:
                            break

                    if feasible_qty_accum <= 0:
                        continue

                    # Accepted match!
                    priority = "CRITICAL" if dest["days_of_cover"] <= 3 else ("HIGH" if dest["days_of_cover"] <= 7 else "MEDIUM")
                    arrival_est = now + timedelta(days=TRANSIT_BUFFER_DAYS)

                    accepted_opportunities.append({
                        "source_facility_id": src_fac.id,
                        "source_facility_name": src_fac.name,
                        "destination_facility_id": dest_fac.id,
                        "destination_facility_name": dest_fac.name,
                        "product_id": prod.id,
                        "product_name": prod.name,
                        "generic_name": prod.generic_name,
                        "strength": prod.strength,
                        "storage_requirements": prod.storage_requirements,
                        "matched_quantity": feasible_qty_accum,
                        "unit": prod.base_unit,
                        "priority": priority,
                        "expected_arrival_at": arrival_est.isoformat(),
                        "batches": feasible_batches,
                        "source_rationale": {
                            "usable_stock": src["surplus_qty"],
                            "surplus_available": src["surplus_qty"],
                            "retained_safety_buffer": int(src["daily_demand"] * SAFETY_STOCK_DAYS),
                            "summary": f"Source has {src['surplus_qty']} surplus units beyond local 37-day forecast requirements."
                        },
                        "destination_rationale": {
                            "current_stock": dest["current_usable"],
                            "days_of_cover": dest["days_of_cover"],
                            "daily_burn_rate": dest["daily_demand"],
                            "unmet_need": dest["unmet_need"],
                            "stockout_prevented": True,
                            "summary": f"Destination has only {dest['days_of_cover']} days of cover. Transfer of {feasible_qty_accum} units restores buffer."
                        },
                        "acceptance_score": round(100.0 - (dest["days_of_cover"] * 4.0), 1)
                    })

        # Sort opportunities by highest priority first
        priority_weights = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}
        accepted_opportunities.sort(key=lambda x: (priority_weights.get(x["priority"], 0), x["matched_quantity"]), reverse=True)

        return {
            "accepted_opportunities": accepted_opportunities,
            "rejected_candidates": rejected_candidates,
            "total_matches": len(accepted_opportunities),
            "total_rejected": len(rejected_candidates)
        }


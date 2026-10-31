import logging
from datetime import datetime, timezone, timedelta, date
from typing import List, Dict, Any, Optional
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.consumption import ConsumptionRecord, PurchaseOrder, PurchaseOrderLine
from app.models.product import Product
from app.models.organization import Facility
from app.models.intelligence import ForecastRun
from app.services.inventory_service import InventoryService

logger = logging.getLogger("mediflow.forecast")


class ForecastService:
    """
    Deterministic, explainable demand forecasting engine.
    Uses transparent weighted moving averages and rolling baselines grounded strictly
    in verified historical consumption records.
    Never uses black-box or non-deterministic LLM-generated numerical predictions.
    """

    @staticmethod
    def aggregate_consumption(
        db: Session,
        facility_id: str,
        product_id: str,
        window_days: int = 90,
        period: str = "daily"
    ) -> Dict[str, Any]:
        """
        Aggregates consumption records at facility-product level.
        Detects missing periods, zero demand, stale data, and insufficient history.
        Preserves the source unit and daily/weekly calendar continuity.
        """
        now = datetime.now(timezone.utc)
        today = now.date()
        start_history_dt = now - timedelta(days=window_days)
        start_history_date = start_history_dt.date()

        # Determine product base unit
        prod = db.query(Product).filter(Product.id == product_id).first()
        base_unit = prod.base_unit if prod else "UNIT"

        # Query consumption records in chronological order
        records = db.query(ConsumptionRecord).filter(
            ConsumptionRecord.facility_id == facility_id,
            ConsumptionRecord.product_id == product_id,
            ConsumptionRecord.consumed_at >= start_history_dt
        ).order_by(ConsumptionRecord.consumed_at.asc()).all()

        warnings: List[str] = []

        if not records:
            warnings.append("Insufficient data: No historical consumption records found for this product.")
            return {
                "facility_id": facility_id,
                "product_id": product_id,
                "period": period,
                "unit": base_unit,
                "total_quantity": 0,
                "history_days": 0,
                "active_days": 0,
                "zero_days": window_days,
                "values": [],
                "daily_series": [],
                "days_since_last": 999,
                "has_insufficient_history": True,
                "has_stale_data": True,
                "has_zero_demand": True,
                "warnings": warnings
            }

        # Sum consumption by calendar date
        daily_map: Dict[date, int] = {}
        for r in records:
            r_date = r.consumed_at.date()
            daily_map[r_date] = daily_map.get(r_date, 0) + r.quantity
            if r.unit:
                base_unit = r.unit

        # Build full continuous calendar range from earliest recorded date in window to today
        min_recorded_date = min(daily_map.keys())
        max_recorded_date = max(daily_map.keys())
        calendar_start = max(min_recorded_date, start_history_date)

        total_calendar_days = (today - calendar_start).days + 1
        history_span_days = (max_recorded_date - min_recorded_date).days + 1
        days_since_last = (today - max_recorded_date).days

        continuous_dates: List[str] = []
        continuous_values: List[int] = []
        active_days = 0
        zero_days = 0
        max_consecutive_zeros = 0
        current_zero_streak = 0

        curr = calendar_start
        while curr <= today:
            val = daily_map.get(curr, 0)
            continuous_dates.append(curr.isoformat())
            continuous_values.append(val)
            if val > 0:
                active_days += 1
                current_zero_streak = 0
            else:
                zero_days += 1
                current_zero_streak += 1
                if current_zero_streak > max_consecutive_zeros:
                    max_consecutive_zeros = current_zero_streak
            curr += timedelta(days=1)

        total_quantity = sum(continuous_values)

        # Detect data quality warnings
        if history_span_days < 14 or active_days < 5:
            warnings.append(
                f"Short history warning: Only {history_span_days} days of history with {active_days} active consumption days. Predictions carry wider confidence intervals."
            )
        if days_since_last > 7:
            warnings.append(f"Stale data warning: Last recorded consumption was {days_since_last} days ago.")
        if total_quantity == 0:
            warnings.append("Zero demand: No consumption recorded throughout the historical period.")
        elif max_consecutive_zeros >= 14:
            warnings.append(f"Data gap detected: {max_consecutive_zeros} consecutive days with zero recorded consumption.")

        # Weekly aggregation if requested
        if period == "weekly":
            weekly_values: List[int] = []
            weekly_dates: List[str] = []
            chunk_size = 7
            for i in range(0, len(continuous_values), chunk_size):
                chunk = continuous_values[i:i + chunk_size]
                weekly_values.append(sum(chunk))
                weekly_dates.append(continuous_dates[i])
            return {
                "facility_id": facility_id,
                "product_id": product_id,
                "period": "weekly",
                "unit": base_unit,
                "total_quantity": total_quantity,
                "history_days": history_span_days,
                "active_days": active_days,
                "zero_days": zero_days,
                "values": weekly_values,
                "daily_series": [{"date": d, "quantity": q} for d, q in zip(weekly_dates, weekly_values)],
                "days_since_last": days_since_last,
                "has_insufficient_history": (history_span_days < 14 or active_days < 5),
                "has_stale_data": (days_since_last > 7),
                "has_zero_demand": (total_quantity == 0),
                "warnings": warnings
            }

        return {
            "facility_id": facility_id,
            "product_id": product_id,
            "period": "daily",
            "unit": base_unit,
            "total_quantity": total_quantity,
            "history_days": history_span_days,
            "active_days": active_days,
            "zero_days": zero_days,
            "values": continuous_values,
            "daily_series": [{"date": d, "quantity": q} for d, q in zip(continuous_dates, continuous_values)],
            "days_since_last": days_since_last,
            "has_insufficient_history": (history_span_days < 14 or active_days < 5),
            "has_stale_data": (days_since_last > 7),
            "has_zero_demand": (total_quantity == 0),
            "warnings": warnings
        }

    @staticmethod
    def calculate_projected_stock(
        usable_stock: int,
        daily_demand: float,
        horizon_days: int = 30,
        inbound_deliveries: Optional[List[Dict[str, Any]]] = None,
        existing_outbound_commitments: int = 0,
        safety_stock: int = 0,
        start_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Calculates time-phased projected inventory trajectory and end-of-period stock:
        projected_stock(horizon) = usable_on_hand - expected_consumption(horizon) + confirmed_inbound(horizon) - existing_outbound_commitments(horizon)

        Guarantees that reservations are not double-counted (usable_stock already excludes reserved stock).
        """
        if start_date is None:
            start_date = datetime.now(timezone.utc).date()

        inbound_map: Dict[str, int] = {}
        total_inbound = 0
        if inbound_deliveries:
            for item in inbound_deliveries:
                d_str = str(item.get("delivery_date", ""))
                qty = int(item.get("quantity", 0))
                inbound_map[d_str] = inbound_map.get(d_str, 0) + qty
                total_inbound += qty

        # Day-by-day time-phased trajectory
        trajectory = []
        current_balance = float(usable_stock)
        # Apply any unreserved outbound commitments on Day 1
        current_balance -= float(existing_outbound_commitments)

        stockout_day: Optional[int] = None
        stockout_date: Optional[str] = None
        safety_stock_breach_day: Optional[int] = None

        for day in range(1, horizon_days + 1):
            day_date = start_date + timedelta(days=day)
            day_str = day_date.isoformat()

            starting = current_balance
            day_inbound = inbound_map.get(day_str, 0)
            day_demand = daily_demand

            ending = max(0.0, starting - day_demand + day_inbound)

            below_safety = (ending < safety_stock)
            is_stockout = (ending <= 0.0)

            if is_stockout and stockout_day is None:
                stockout_day = day
                stockout_date = day_str
            if below_safety and safety_stock_breach_day is None:
                safety_stock_breach_day = day

            trajectory.append({
                "day": day,
                "date": day_str,
                "starting_stock": int(round(starting)),
                "demand": round(day_demand, 1),
                "inbound": day_inbound,
                "ending_stock": int(round(ending)),
                "below_safety_stock": below_safety,
                "is_stockout": is_stockout
            })

            current_balance = ending

        projected_consumption = round(daily_demand * horizon_days, 1)
        end_stock = int(round(current_balance))

        return {
            "usable_stock_start": usable_stock,
            "projected_consumption_horizon": projected_consumption,
            "confirmed_inbound_horizon": total_inbound,
            "outbound_commitments": existing_outbound_commitments,
            "projected_stock_end": end_stock,
            "stockout_day": stockout_day,
            "stockout_date": stockout_date,
            "safety_stock_breach_day": safety_stock_breach_day,
            "trajectory": trajectory
        }

    @staticmethod
    def calculate_forecast(
        db: Session,
        facility_id: str,
        product_id: str,
        horizon_days: int = 30
    ) -> Dict[str, Any]:
        """
        Generates an evidence-rich, transparent baseline forecast using weighted
        moving averages and calendar projections.
        """
        now = datetime.now(timezone.utc)
        today = now.date()

        # 1. Aggregate historical consumption
        agg = ForecastService.aggregate_consumption(
            db, facility_id=facility_id, product_id=product_id, window_days=90, period="daily"
        )
        warnings = list(agg["warnings"])
        base_unit = agg["unit"]
        daily_series = agg["values"]

        # Handle zero or missing historical data
        if not daily_series or agg["total_quantity"] == 0:
            wma_daily = 0.0
            std_dev = 0.0
            confidence_score = 0.1
            data_quality_score = 0.2 if daily_series else 0.0
            daily_estimates = []
            for i in range(1, horizon_days + 1):
                f_date = today + timedelta(days=i)
                daily_estimates.append({
                    "date": f_date.isoformat(),
                    "estimated_demand": 0.0,
                    "confidence_lower": 0.0,
                    "confidence_upper": 0.0
                })
        else:
            # Weighted moving average: exponential recency weights
            n = len(daily_series)
            if n < 3:
                # Pad for statistical stability
                padded = daily_series + [daily_series[-1]] * (3 - n)
                weights = np.array([0.2, 0.3, 0.5])
                wma_daily = float(np.dot(padded, weights))
                std_dev = float(np.std(padded)) if len(padded) > 1 else wma_daily * 0.2
            else:
                # More weight on recent periods
                weights = np.exp(np.linspace(-1.5, 0, n))
                weights /= weights.sum()
                wma_daily = float(np.dot(daily_series, weights))
                std_dev = float(np.std(daily_series))

            # Quality metrics
            cv = (std_dev / wma_daily) if wma_daily > 0 else 1.0

            data_quality_score = 1.0
            if agg["history_days"] < 30:
                data_quality_score -= 0.2
            if agg["days_since_last"] > 5:
                data_quality_score -= 0.25
            if agg["active_days"] < 10:
                data_quality_score -= 0.15
            data_quality_score = max(0.2, min(1.0, data_quality_score))

            confidence_score = max(0.25, min(0.95, 1.0 - (cv * 0.25))) * data_quality_score

            # Daily estimates with weekday calendar adjustments
            daily_estimates = []
            for i in range(1, horizon_days + 1):
                future_date = today + timedelta(days=i)
                weekday = future_date.weekday()
                # Outpatient and clinical elective usage is slightly lower on weekends
                day_factor = 0.85 if weekday >= 5 else 1.05
                day_estimate = round(wma_daily * day_factor, 1)
                lower_bound = max(0.0, round(day_estimate - (1.645 * std_dev * 0.6), 1))
                upper_bound = round(day_estimate + (1.645 * std_dev * 0.6), 1)

                daily_estimates.append({
                    "date": future_date.isoformat(),
                    "estimated_demand": day_estimate,
                    "confidence_lower": lower_bound,
                    "confidence_upper": upper_bound
                })

        # Calculate 7-day and 30-day summaries
        demand_7d = round(sum(d["estimated_demand"] for d in daily_estimates[:7]), 1)
        demand_30d = round(sum(d["estimated_demand"] for d in daily_estimates[:30]), 1)
        projected_total = round(sum(d["estimated_demand"] for d in daily_estimates[:horizon_days]), 1)

        # 2. Fetch inventory and inbound purchase orders for projected stock calculation
        inv_summary = InventoryService.get_product_stock_summary(db, facility_id, product_id)
        usable_stock = inv_summary.get("total_usable", 0)

        # Confirmed inbound purchase orders
        pos = db.query(PurchaseOrder).join(PurchaseOrderLine).filter(
            PurchaseOrder.facility_id == facility_id,
            PurchaseOrder.status.in_(["CONFIRMED", "IN_TRANSIT", "PLACED"]),
            PurchaseOrderLine.product_id == product_id
        ).all()

        inbound_deliveries = []
        for po in pos:
            for line in po.lines:
                if line.product_id == product_id:
                    remaining_qty = max(0, line.quantity_ordered - line.quantity_received)
                    if remaining_qty > 0 and po.expected_delivery_at:
                        inbound_deliveries.append({
                            "po_id": po.id,
                            "delivery_date": po.expected_delivery_at.date(),
                            "quantity": remaining_qty
                        })

        # Calculate stock trajectory
        stock_proj = ForecastService.calculate_projected_stock(
            usable_stock=usable_stock,
            daily_demand=round(wma_daily, 2),
            horizon_days=horizon_days,
            inbound_deliveries=inbound_deliveries,
            existing_outbound_commitments=0,
            safety_stock=int(round(wma_daily * 7)),
            start_date=today
        )

        # 3. Persist ForecastRun in database
        forecast_run = ForecastRun(
            facility_id=facility_id,
            product_id=product_id,
            model_name="WEIGHTED_MOVING_AVERAGE",
            horizon_start=now,
            horizon_end=now + timedelta(days=horizon_days),
            forecast_payload={
                "projected_total_demand": projected_total,
                "daily_average_demand": round(wma_daily, 2),
                "demand_7d": demand_7d,
                "demand_30d": demand_30d,
                "unit": base_unit,
                "daily_estimates": daily_estimates,
                "history_days": agg["history_days"],
                "active_days": agg["active_days"],
                "projected_stock_end": stock_proj["projected_stock_end"],
                "stockout_date": stock_proj["stockout_date"]
            },
            metrics={
                "confidence_score": round(confidence_score, 2),
                "data_quality_score": round(data_quality_score, 2),
                "warnings": warnings,
                "method_description": "Explainable statistical baseline using weighted moving average with recency weighting and calendar smoothing. Not predictive AI."
            },
            data_quality_score=round(data_quality_score, 2)
        )
        db.add(forecast_run)
        db.flush()

        return {
            "id": forecast_run.id,
            "facility_id": facility_id,
            "product_id": product_id,
            "model_name": "WEIGHTED_MOVING_AVERAGE",
            "horizon_days": horizon_days,
            "projected_total_demand": projected_total,
            "daily_average_demand": round(wma_daily, 2),
            "demand_7d": demand_7d,
            "demand_30d": demand_30d,
            "unit": base_unit,
            "confidence_score": round(confidence_score, 2),
            "data_quality_score": round(data_quality_score, 2),
            "warnings": warnings,
            "daily_estimates": daily_estimates,
            "projected_stock_trajectory": stock_proj["trajectory"],
            "summary": {
                "usable_stock": usable_stock,
                "projected_stock_end": stock_proj["projected_stock_end"],
                "confirmed_inbound": stock_proj["confirmed_inbound_horizon"],
                "stockout_date": stock_proj["stockout_date"],
                "method": "WEIGHTED_MOVING_AVERAGE (Deterministic Baseline)"
            }
        }

    @staticmethod
    def run_batch_forecasts(
        db: Session,
        facility_id: Optional[str] = None,
        product_id: Optional[str] = None,
        horizon_days: int = 30
    ) -> Dict[str, Any]:
        """
        Executes and records forecasts across all active facilities and products.
        """
        fac_q = db.query(Facility).filter(Facility.status == "ACTIVE")
        if facility_id:
            fac_q = fac_q.filter(Facility.id == facility_id)
        facilities = fac_q.all()

        prod_q = db.query(Product).filter(Product.status == "ACTIVE")
        if product_id:
            prod_q = prod_q.filter(Product.id == product_id)
        products = prod_q.all()

        runs = []
        for fac in facilities:
            for prod in products:
                fc = ForecastService.calculate_forecast(
                    db, facility_id=fac.id, product_id=prod.id, horizon_days=horizon_days
                )
                runs.append({
                    "forecast_id": fc["id"],
                    "facility_id": fac.id,
                    "product_id": prod.id,
                    "daily_average_demand": fc["daily_average_demand"],
                    "projected_total_demand": fc["projected_total_demand"],
                    "confidence_score": fc["confidence_score"],
                    "warnings_count": len(fc.get("warnings", []))
                })

        db.commit()
        return {
            "total_runs": len(runs),
            "runs": runs
        }

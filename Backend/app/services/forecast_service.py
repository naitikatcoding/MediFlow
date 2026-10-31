from datetime import datetime, timezone, timedelta, date
from typing import List, Dict, Any, Optional
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.consumption import ConsumptionRecord
from app.models.intelligence import ForecastRun


class ForecastService:
    @staticmethod
    def calculate_forecast(
        db: Session,
        facility_id: str,
        product_id: str,
        horizon_days: int = 30
    ) -> Dict[str, Any]:
        """
        Deterministic, explainable demand forecast using weighted moving averages
        and rolling baselines grounded in historical consumption records.
        """
        now = datetime.now(timezone.utc)
        start_history = now - timedelta(days=90)

        # Retrieve consumption records ordered by date
        records = db.query(ConsumptionRecord).filter(
            ConsumptionRecord.facility_id == facility_id,
            ConsumptionRecord.product_id == product_id,
            ConsumptionRecord.consumed_at >= start_history
        ).order_by(ConsumptionRecord.consumed_at.asc()).all()

        warnings = []
        if not records:
            warnings.append("Insufficient data: No historical consumption records found for this product.")
            return {
                "id": "unrecorded",
                "facility_id": facility_id,
                "product_id": product_id,
                "model_name": "WEIGHTED_MOVING_AVERAGE",
                "horizon_days": horizon_days,
                "projected_total_demand": 0.0,
                "daily_average_demand": 0.0,
                "confidence_score": 0.1,
                "data_quality_score": 0.0,
                "warnings": warnings,
                "daily_estimates": []
            }

        history_days = (records[-1].consumed_at.date() - records[0].consumed_at.date()).days + 1
        days_since_last = (now.date() - records[-1].consumed_at.date()).days

        if history_days < 14:
            warnings.append(f"Short history warning: Only {history_days} days of history available. Predictions have wider intervals.")
        if days_since_last > 7:
            warnings.append(f"Stale data warning: Last recorded consumption was {days_since_last} days ago.")

        # Aggregate daily consumption
        daily_dict = {}
        for r in records:
            day_str = r.consumed_at.date().isoformat()
            daily_dict[day_str] = daily_dict.get(day_str, 0) + r.quantity

        daily_series = list(daily_dict.values())
        if len(daily_series) < 3:
            daily_series = daily_series + [daily_series[-1]] * (3 - len(daily_series))

        # Exponential weights for weighted moving average (more weight on recent days)
        n = len(daily_series)
        weights = np.exp(np.linspace(-1.5, 0, n))
        weights /= weights.sum()

        wma_daily = float(np.dot(daily_series, weights))
        std_dev = float(np.std(daily_series)) if len(daily_series) > 1 else wma_daily * 0.2

        # Data quality score
        data_quality_score = 1.0
        if history_days < 30:
            data_quality_score -= 0.2
        if days_since_last > 5:
            data_quality_score -= 0.25
        data_quality_score = max(0.2, min(1.0, data_quality_score))

        # Confidence score based on volatility (coefficient of variation)
        cv = (std_dev / wma_daily) if wma_daily > 0 else 1.0
        confidence_score = max(0.3, min(0.95, 1.0 - (cv * 0.3))) * data_quality_score

        # Projected horizon estimates
        daily_estimates = []
        curr_date = now.date()
        for i in range(1, horizon_days + 1):
            future_date = curr_date + timedelta(days=i)
            # Slight weekday dampening/boosting for weekends
            weekday = future_date.weekday()
            day_factor = 0.85 if weekday >= 5 else 1.05
            day_estimate = round(wma_daily * day_factor, 1)
            lower_bound = max(0.0, round(day_estimate - (1.645 * std_dev * 0.7), 1))
            upper_bound = round(day_estimate + (1.645 * std_dev * 0.7), 1)

            daily_estimates.append({
                "date": future_date.isoformat(),
                "estimated_demand": day_estimate,
                "confidence_lower": lower_bound,
                "confidence_upper": upper_bound
            })

        projected_total = round(sum(d["estimated_demand"] for d in daily_estimates), 1)

        # Persist or update ForecastRun in DB
        forecast_run = ForecastRun(
            facility_id=facility_id,
            product_id=product_id,
            model_name="WEIGHTED_MOVING_AVERAGE",
            horizon_start=now,
            horizon_end=now + timedelta(days=horizon_days),
            forecast_payload={
                "projected_total_demand": projected_total,
                "daily_average_demand": round(wma_daily, 2),
                "daily_estimates": daily_estimates,
                "history_days": history_days
            },
            metrics={
                "confidence_score": round(confidence_score, 2),
                "data_quality_score": round(data_quality_score, 2),
                "cv": round(cv, 2),
                "warnings": warnings
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
            "confidence_score": round(confidence_score, 2),
            "data_quality_score": round(data_quality_score, 2),
            "warnings": warnings,
            "daily_estimates": daily_estimates
        }


from typing import Optional, List, Union
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.services.forecast_service import ForecastService
from app.models.organization import Facility
from app.models.product import Product
from app.schemas.domain import (
    ForecastResponse,
    ForecastRunRequest,
    ForecastRunBatchResponse
)

router = APIRouter(prefix="/forecasts", tags=["forecasts"])


@router.post("/run", response_model=ForecastRunBatchResponse)
def trigger_forecast_run(
    request: Optional[ForecastRunRequest] = Body(None),
    db: Session = Depends(get_db)
):
    """
    Triggers deterministic demand forecast computation and persists ForecastRun records.
    Optionally scoped to a specific facility_id and/or product_id.
    """
    fac_id = request.facility_id if request else None
    prod_id = request.product_id if request else None
    horizon = request.horizon_days if request and request.horizon_days else 30

    try:
        result = ForecastService.run_batch_forecasts(
            db=db,
            facility_id=fac_id,
            product_id=prod_id,
            horizon_days=horizon
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Forecast run failed: {str(e)}")


@router.get("", response_model=Union[ForecastResponse, List[ForecastResponse]])
def get_forecast(
    facility_id: Optional[str] = Query(None, description="Target facility ID"),
    product_id: Optional[str] = Query(None, description="Target medicine product ID"),
    horizon_days: int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db)
):
    """
    Retrieves explainable baseline demand forecast.
    If both facility_id and product_id are supplied, returns the detailed single forecast.
    If either or both are omitted, returns a list of forecasts across all active facilities/products.
    """
    try:
        # If both IDs are provided, return the single detailed ForecastResponse
        if facility_id and product_id:
            return ForecastService.calculate_forecast(
                db=db,
                facility_id=facility_id,
                product_id=product_id,
                horizon_days=horizon_days
            )

        # Otherwise, return list across matching active facilities & products
        fac_q = db.query(Facility).filter(Facility.status == "ACTIVE")
        if facility_id:
            fac_q = fac_q.filter(Facility.id == facility_id)
        facilities = fac_q.all()

        prod_q = db.query(Product).filter(Product.status == "ACTIVE")
        if product_id:
            prod_q = prod_q.filter(Product.id == product_id)
        products = prod_q.all()

        results = []
        for fac in facilities:
            for prod in products:
                fc = ForecastService.calculate_forecast(
                    db=db,
                    facility_id=fac.id,
                    product_id=prod.id,
                    horizon_days=horizon_days
                )
                results.append(fc)
        return results

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

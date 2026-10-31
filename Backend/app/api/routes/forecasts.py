from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.services.forecast_service import ForecastService
from app.schemas.domain import ForecastResponse

router = APIRouter(prefix="/forecasts", tags=["forecasts"])


@router.get("", response_model=ForecastResponse)
def get_forecast(
    facility_id: str = Query(..., description="Target facility ID"),
    product_id: str = Query(..., description="Target medicine product ID"),
    horizon_days: int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db)
):
    try:
        return ForecastService.calculate_forecast(
            db=db,
            facility_id=facility_id,
            product_id=product_id,
            horizon_days=horizon_days
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


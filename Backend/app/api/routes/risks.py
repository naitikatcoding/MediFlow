from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.services.risk_service import RiskService
from app.schemas.domain import RiskAssessmentResponse

router = APIRouter(prefix="/risks", tags=["risks"])


@router.get("", response_model=List[RiskAssessmentResponse])
def get_risks(
    facility_id: Optional[str] = None,
    product_id: Optional[str] = None,
    risk_type: Optional[str] = None, # STOCKOUT_RISK, EXPIRY_RISK, SURPLUS_AVAILABLE
    risk_level: Optional[str] = None, # CRITICAL, HIGH, MEDIUM
    db: Session = Depends(get_db)
):
    all_risks = RiskService.evaluate_risks(db, facility_id=facility_id, product_id=product_id)
    if risk_type:
        all_risks = [r for r in all_risks if r["risk_type"] == risk_type]
    if risk_level:
        all_risks = [r for r in all_risks if r["risk_level"] == risk_level]
    return all_risks


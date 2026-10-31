from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.services.risk_service import RiskService
from app.schemas.domain import RiskAssessmentResponse, RisksSummaryResponse

router = APIRouter(prefix="/risks", tags=["risks"])


@router.get("", response_model=List[RiskAssessmentResponse])
def get_risks(
    facility_id: Optional[str] = None,
    product_id: Optional[str] = None,
    risk_type: Optional[str] = None, # STOCKOUT_RISK, EXPIRY_RISK, SURPLUS_AVAILABLE
    risk_level: Optional[str] = None, # CRITICAL, HIGH, MEDIUM, LOW, SAFE
    db: Session = Depends(get_db)
):
    """
    Evaluates and returns clinical supply risks across facilities and products.
    Supports filtering by facility_id, product_id, risk_type, and risk_level.
    """
    all_risks = RiskService.evaluate_risks(db, facility_id=facility_id, product_id=product_id)
    if risk_type:
        all_risks = [r for r in all_risks if r["risk_type"] == risk_type]
    if risk_level:
        all_risks = [r for r in all_risks if r["risk_level"] == risk_level]
    return all_risks


@router.get("/summary", response_model=RisksSummaryResponse)
def get_risks_summary(db: Session = Depends(get_db)):
    """
    Returns aggregated risk summary metrics: stockout risks, expiry risks,
    transferable surpluses, and facility breakdowns.
    """
    return RiskService.get_risks_summary(db)


@router.get("/{risk_id}", response_model=RiskAssessmentResponse)
def get_risk_detail(risk_id: str, db: Session = Depends(get_db)):
    """
    Retrieves full evidence breakdown and calculation inputs for a specific risk assessment.
    """
    risk = RiskService.get_risk_by_id(db, risk_id)
    if not risk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Risk assessment with ID '{risk_id}' not found."
        )
    return risk

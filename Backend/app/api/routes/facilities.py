from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models.organization import Facility
from app.schemas.domain import FacilityResponse

router = APIRouter(prefix="/facilities", tags=["facilities"])


@router.get("", response_model=List[FacilityResponse])
def list_facilities(db: Session = Depends(get_db)):
    return db.query(Facility).all()


@router.get("/{facility_id}", response_model=FacilityResponse)
def get_facility(facility_id: str, db: Session = Depends(get_db)):
    fac = db.query(Facility).filter(Facility.id == facility_id).first()
    if not fac:
        raise HTTPException(status_code=404, detail="Facility not found")
    return fac


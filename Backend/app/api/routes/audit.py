from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models.audit import AuditEvent

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/events")
def list_audit_events(
    facility_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    query = db.query(AuditEvent)
    if facility_id:
        query = query.filter(AuditEvent.facility_id == facility_id)
    if entity_type:
        query = query.filter(AuditEvent.entity_type == entity_type)
    return query.order_by(AuditEvent.created_at.desc()).limit(limit).all()


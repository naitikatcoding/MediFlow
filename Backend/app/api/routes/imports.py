from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models.audit import ImportJob
from app.services.import_service import ImportService
from app.schemas.domain import ImportJobResponse, ImportJobErrorDetail

router = APIRouter(prefix="/imports", tags=["imports"])


@router.get("", response_model=List[ImportJobResponse])
def list_import_jobs(
    facility_id: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """List recent data import jobs and their execution statuses."""
    query = db.query(ImportJob)
    if facility_id:
        query = query.filter(ImportJob.facility_id == facility_id)
    return query.order_by(ImportJob.created_at.desc()).limit(limit).all()


@router.get("/{job_id}", response_model=ImportJobResponse)
def get_import_job(job_id: str, db: Session = Depends(get_db)):
    """Retrieve status and summary of a specific import job."""
    job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")
    return job


@router.get("/{job_id}/errors", response_model=ImportJobErrorDetail)
def get_import_job_errors(job_id: str, db: Session = Depends(get_db)):
    """Retrieve detailed validation errors and rejected rows for an import job."""
    job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")

    errors = []
    if job.error_summary and isinstance(job.error_summary, dict):
        errors = job.error_summary.get("errors", [])

    return ImportJobErrorDetail(
        job_id=job.id,
        facility_id=job.facility_id,
        status=job.status,
        row_count=job.row_count,
        accepted_count=job.accepted_count,
        rejected_count=job.rejected_count,
        errors=errors
    )


@router.post("", response_model=ImportJobResponse)
async def upload_inventory_csv(
    file: Optional[UploadFile] = File(None),
    csv_data: Optional[str] = Form(None),
    facility_id: Optional[str] = Form(None),
    actor_id: Optional[str] = Form("pharmacist_upload"),
    db: Session = Depends(get_db)
):
    """
    Ingest medicine inventory and batch lots via CSV upload.
    Validates required columns, facility mappings, lot integrity, and expiry dates.
    """
    content = ""
    filename = "inventory_import.csv"

    if file:
        filename = file.filename or "uploaded_inventory.csv"
        raw_bytes = await file.read()
        content = raw_bytes.decode("utf-8", errors="replace")
    elif csv_data:
        content = csv_data
    else:
        raise HTTPException(
            status_code=400,
            detail="Must provide either a CSV file or csv_data string."
        )

    if not content.strip():
        raise HTTPException(status_code=400, detail="CSV payload is empty.")

    job = ImportService.process_inventory_csv(
        db=db,
        csv_text=content,
        target_facility_id=facility_id,
        filename=filename,
        actor_id=actor_id
    )

    return job

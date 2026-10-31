import csv
import io
import uuid
from datetime import datetime, timezone, date
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.audit import ImportJob, AuditEvent
from app.models.organization import Facility
from app.models.product import Product, Batch
from app.services.ledger_service import LedgerService


class ImportService:
    @staticmethod
    def parse_date(date_str: str) -> Optional[date]:
        if not date_str:
            return None
        date_str = str(date_str).strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def process_inventory_csv(
        db: Session,
        csv_text: str,
        target_facility_id: Optional[str] = None,
        filename: Optional[str] = "inventory_import.csv",
        actor_id: Optional[str] = "system_import"
    ) -> ImportJob:
        """
        Parses, validates, and processes an inventory CSV import job.
        Maintains row-level rejection reporting and audit logs.
        """
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Create initial processing job record
        job = ImportJob(
            id=job_id,
            facility_id=target_facility_id or "NETWORK",
            source_type="CSV_IMPORT",
            filename=filename,
            status="PROCESSING",
            row_count=0,
            accepted_count=0,
            rejected_count=0,
            error_summary={},
            created_at=now
        )
        db.add(job)
        db.commit()

        # Parse CSV
        f = io.StringIO(csv_text.strip())
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            job.status = "FAILED"
            job.error_summary = {"errors": [{"row": 0, "error": "CSV file contains no headers or is empty."}]}
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            return job

        # Normalize field names
        field_map = {}
        for fn in reader.fieldnames:
            clean = fn.strip().lower().replace(" ", "_").replace("-", "_")
            field_map[clean] = fn

        # Pre-cache facilities and products for fast lookup
        facilities_by_id = {f.id: f for f in db.query(Facility).all()}
        facilities_by_name = {f.name.lower(): f for f in facilities_by_id.values()}
        products_by_code = {p.internal_code.lower(): p for p in db.query(Product).all()}
        products_by_id = {p.id: p for p in db.query(Product).all()}

        accepted_rows = 0
        rejected_rows = 0
        errors = []
        seen_keys = set()

        row_idx = 1
        for row in reader:
            row_idx += 1
            # Extract row values using normalized map
            fac_val = (
                row.get(field_map.get("facility_id", "")) or
                row.get(field_map.get("facility", "")) or
                target_facility_id
            )
            prod_val = (
                row.get(field_map.get("product_code", "")) or
                row.get(field_map.get("product_id", "")) or
                row.get(field_map.get("medicine", "")) or
                row.get(field_map.get("code", ""))
            )
            lot_val = (
                row.get(field_map.get("lot_number", "")) or
                row.get(field_map.get("batch_number", "")) or
                row.get(field_map.get("batch_id", "")) or
                row.get(field_map.get("lot", ""))
            )
            expiry_val = (
                row.get(field_map.get("expiry_date", "")) or
                row.get(field_map.get("expiry", "")) or
                row.get(field_map.get("exp_date", ""))
            )
            qty_val = (
                row.get(field_map.get("quantity", "")) or
                row.get(field_map.get("on_hand", "")) or
                row.get(field_map.get("qty", ""))
            )
            unit_val = (
                row.get(field_map.get("unit", "")) or
                row.get(field_map.get("base_unit", "")) or
                "UNIT"
            )
            mfg_date_val = row.get(field_map.get("manufacturing_date", "")) or row.get(field_map.get("mfg_date", ""))
            mfr_val = row.get(field_map.get("manufacturer", "")) or "Generic Pharma Ltd"
            movement_type_val = row.get(field_map.get("movement_type", "")) or "PURCHASE_RECEIPT"

            # Validation 1: Required fields
            if not fac_val or not prod_val or not lot_val or not expiry_val or not qty_val:
                rejected_rows += 1
                errors.append({
                    "row": row_idx,
                    "error": "Missing mandatory columns (facility, product_code, lot_number, expiry_date, quantity)."
                })
                continue

            # Validation 2: Facility exists
            facility = facilities_by_id.get(fac_val.strip()) or facilities_by_name.get(fac_val.strip().lower())
            if not facility:
                rejected_rows += 1
                errors.append({
                    "row": row_idx,
                    "facility": fac_val,
                    "error": f"Facility '{fac_val}' not recognized."
                })
                continue

            # Update job facility_id if singular
            if job.facility_id == "NETWORK" and target_facility_id:
                job.facility_id = facility.id

            # Validation 3: Product exists
            product = products_by_code.get(prod_val.strip().lower()) or products_by_id.get(prod_val.strip())
            if not product:
                rejected_rows += 1
                errors.append({
                    "row": row_idx,
                    "product": prod_val,
                    "error": f"Product '{prod_val}' not found in catalogue."
                })
                continue

            # Validation 4: Quantity is a positive integer
            try:
                quantity = int(qty_val.strip())
                if quantity <= 0:
                    raise ValueError()
            except Exception:
                rejected_rows += 1
                errors.append({
                    "row": row_idx,
                    "quantity": qty_val,
                    "error": f"Quantity must be a positive integer, received '{qty_val}'."
                })
                continue

            # Validation 5: Expiry date parsing
            expiry_date = ImportService.parse_date(expiry_val)
            if not expiry_date:
                rejected_rows += 1
                errors.append({
                    "row": row_idx,
                    "expiry_date": expiry_val,
                    "error": f"Invalid expiry date format: '{expiry_val}'. Use YYYY-MM-DD or DD/MM/YYYY."
                })
                continue

            # Validation 6: Duplicate detection in same file
            lot_clean = lot_val.strip()
            dedup_key = f"{facility.id}_{product.id}_{lot_clean}"
            if dedup_key in seen_keys:
                rejected_rows += 1
                errors.append({
                    "row": row_idx,
                    "lot": lot_clean,
                    "error": f"Duplicate batch entry '{lot_clean}' in current import file."
                })
                continue
            seen_keys.add(dedup_key)

            # Validation 7: Unit validation against catalogue
            clean_unit = unit_val.strip().upper()
            if product.base_unit and clean_unit != "UNIT" and product.base_unit != "UNIT":
                if clean_unit != product.base_unit.upper():
                    rejected_rows += 1
                    errors.append({
                        "row": row_idx,
                        "unit": clean_unit,
                        "error": f"Unit mismatch: Product '{product.name}' requires '{product.base_unit}', got '{clean_unit}'."
                    })
                    continue

            # Processing valid row: Create or retrieve Batch
            mfg_date = ImportService.parse_date(mfg_date_val) if mfg_date_val else None
            batch = db.query(Batch).filter(
                Batch.product_id == product.id,
                Batch.manufacturer_lot_number == lot_clean
            ).first()

            if not batch:
                batch = Batch(
                    id=str(uuid.uuid4()),
                    product_id=product.id,
                    manufacturer_lot_number=lot_clean,
                    manufacturing_date=mfg_date,
                    expiry_date=expiry_date,
                    manufacturer=mfr_val.strip(),
                    quality_status="RELEASED",
                    created_at=datetime.now(timezone.utc)
                )
                db.add(batch)
                db.flush()

            # Record inventory movement via LedgerService
            idempotency_key = f"import_{job_id}_row_{row_idx}_{lot_clean}"
            try:
                LedgerService.record_movement(
                    db=db,
                    facility_id=facility.id,
                    batch_id=batch.id,
                    movement_type=movement_type_val if movement_type_val in LedgerService.VALID_MOVEMENT_TYPES else "PURCHASE_RECEIPT",
                    quantity_delta=quantity,
                    unit=clean_unit,
                    reference_type="IMPORT_JOB",
                    reference_id=job.id,
                    actor_id=actor_id,
                    idempotency_key=idempotency_key,
                    reason=f"CSV Import from '{filename}', row {row_idx}",
                    metadata_json={"import_job_id": job.id, "row": row_idx}
                )
                accepted_rows += 1
            except Exception as e:
                rejected_rows += 1
                errors.append({
                    "row": row_idx,
                    "error": f"Ledger recording error: {str(e)}"
                })

        db.commit()

        # Update Job summary
        job.row_count = accepted_rows + rejected_rows
        job.accepted_count = accepted_rows
        job.rejected_count = rejected_rows
        job.status = "COMPLETED" if accepted_rows > 0 else ("FAILED" if rejected_rows > 0 else "COMPLETED")
        job.error_summary = {
            "errors": errors[:50],
            "total_errors": len(errors)
        }
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

        return job

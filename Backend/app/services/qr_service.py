import io
import base64
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import qrcode
from sqlalchemy.orm import Session
from app.models.transfer import Transfer, TransferPackage, SerializedLabel, ScanEvent
from app.models.product import Batch, Product
from app.models.organization import Facility
from app.core.security import hash_token
from app.services.ledger_service import LedgerService


class QRService:
    @staticmethod
    def generate_qr_image_data_uri(token: str) -> str:
        """Generates a high-contrast PNG QR code and returns it as a base64 Data URI."""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(token)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
        
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{img_b64}"

    @staticmethod
    def process_scan(
        db: Session,
        token: str,
        facility_id: str,
        user_id: str,
        scan_type: str, # DISPATCH or RECEIVE
        idempotency_key: str,
        accepted_quantity: Optional[int] = None,
        damaged_quantity: int = 0,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Server-side authenticated scan processor with replay protection,
        wrong-facility rejection, duplicate-scan rejection, and atomic ledger posting.
        """
        now = datetime.now(timezone.utc)
        thash = hash_token(token)

        # 1. Idempotency check: prevent replay of the same scan submission
        if idempotency_key:
            prev_scan = db.query(ScanEvent).filter(
                ScanEvent.idempotency_key == idempotency_key
            ).first()
            if prev_scan:
                return {
                    "success": prev_scan.result == "SUCCESS",
                    "scan_type": scan_type,
                    "status": prev_scan.result,
                    "message": "Duplicate scan submission detected via idempotency key. Original result returned.",
                    "ledger_updated": False,
                    "timestamp": prev_scan.scanned_at
                }

        # 2. Look up label by SHA-256 hash
        label = db.query(SerializedLabel).filter(SerializedLabel.token_hash == thash).first()
        if not label:
            return {
                "success": False,
                "scan_type": scan_type,
                "status": "TOKEN_NOT_FOUND",
                "message": "Verification failed: QR label token not recognized in platform registry.",
                "ledger_updated": False,
                "timestamp": now
            }

        package = db.query(TransferPackage).filter(TransferPackage.id == label.transfer_package_id).first()
        transfer = db.query(Transfer).filter(Transfer.id == package.transfer_id).first()
        batch = db.query(Batch).filter(Batch.id == package.batch_id).first()
        product = db.query(Product).filter(Product.id == batch.product_id).first()

        # 3. Handle DISPATCH scan
        if scan_type.upper() == "DISPATCH":
            # Facility boundary check
            if transfer.source_facility_id != facility_id:
                ScanEvent_record = ScanEvent(
                    serialized_label_id=label.id,
                    transfer_id=transfer.id,
                    facility_id=facility_id,
                    user_id=user_id,
                    scan_type="DISPATCH",
                    result="WRONG_FACILITY",
                    idempotency_key=idempotency_key,
                    metadata_json={"attempted_facility": facility_id, "expected_facility": transfer.source_facility_id}
                )
                db.add(ScanEvent_record)
                db.commit()
                return {
                    "success": False,
                    "scan_type": "DISPATCH",
                    "status": "WRONG_FACILITY",
                    "message": f"Security violation: Dispatch scan must occur at source facility ({transfer.source_facility_id}). Current facility ({facility_id}) rejected.",
                    "ledger_updated": False,
                    "timestamp": now
                }

            # State check
            if label.status == "DISPATCHED" or label.status == "RECEIVED":
                ScanEvent_record = ScanEvent(
                    serialized_label_id=label.id,
                    transfer_id=transfer.id,
                    facility_id=facility_id,
                    user_id=user_id,
                    scan_type="DISPATCH",
                    result="ALREADY_DISPATCHED",
                    idempotency_key=idempotency_key
                )
                db.add(ScanEvent_record)
                db.commit()
                return {
                    "success": False,
                    "scan_type": "DISPATCH",
                    "status": "ALREADY_DISPATCHED",
                    "message": f"Label {label.id[:8]} has already been dispatched. Duplicate dispatch scan rejected.",
                    "ledger_updated": False,
                    "timestamp": now
                }

            # Execute valid dispatch
            label.status = "DISPATCHED"
            package.status = "DISPATCHED"
            transfer.status = "IN_TRANSIT"
            transfer.dispatched_at = now

            # Decrement source stock from reserved on-hand
            LedgerService.record_movement(
                db=db,
                facility_id=transfer.source_facility_id,
                batch_id=package.batch_id,
                movement_type="TRANSFER_DISPATCH",
                quantity_delta=-package.quantity,
                unit=package.unit,
                reference_type="TRANSFER_DISPATCH",
                reference_id=transfer.id,
                actor_id=user_id,
                idempotency_key=f"DISPATCH_{package.id}_{idempotency_key}",
                reason=f"Verified physical dispatch of package {package.package_reference}"
            )

            scan_record = ScanEvent(
                serialized_label_id=label.id,
                transfer_id=transfer.id,
                facility_id=facility_id,
                user_id=user_id,
                scan_type="DISPATCH",
                result="SUCCESS",
                idempotency_key=idempotency_key,
                metadata_json={"package_ref": package.package_reference, "qty": package.quantity}
            )
            db.add(scan_record)
            db.commit()

            return {
                "success": True,
                "scan_type": "DISPATCH",
                "status": "DISPATCHED",
                "message": f"Package {package.package_reference} dispatched successfully. Transfer is now IN TRANSIT.",
                "transfer_id": transfer.id,
                "package_id": package.id,
                "product_name": product.name,
                "lot_number": batch.manufacturer_lot_number,
                "expiry_date": str(batch.expiry_date),
                "verified_quantity": package.quantity,
                "ledger_updated": True,
                "timestamp": now
            }

        # 4. Handle RECEIVE scan
        elif scan_type.upper() == "RECEIVE":
            # Facility boundary check
            if transfer.destination_facility_id != facility_id:
                ScanEvent_record = ScanEvent(
                    serialized_label_id=label.id,
                    transfer_id=transfer.id,
                    facility_id=facility_id,
                    user_id=user_id,
                    scan_type="RECEIVE",
                    result="WRONG_FACILITY",
                    idempotency_key=idempotency_key,
                    metadata_json={"attempted_facility": facility_id, "expected_facility": transfer.destination_facility_id}
                )
                db.add(ScanEvent_record)
                db.commit()
                return {
                    "success": False,
                    "scan_type": "RECEIVE",
                    "status": "WRONG_FACILITY",
                    "message": f"Routing violation: Package was destined for facility {transfer.destination_facility_id}, but scanned at {facility_id}. Receipt rejected.",
                    "ledger_updated": False,
                    "timestamp": now
                }

            # Duplicate receipt prevention
            if label.status == "RECEIVED":
                ScanEvent_record = ScanEvent(
                    serialized_label_id=label.id,
                    transfer_id=transfer.id,
                    facility_id=facility_id,
                    user_id=user_id,
                    scan_type="RECEIVE",
                    result="ALREADY_RECEIVED",
                    idempotency_key=idempotency_key
                )
                db.add(ScanEvent_record)
                db.commit()
                return {
                    "success": False,
                    "scan_type": "RECEIVE",
                    "status": "ALREADY_RECEIVED",
                    "message": f"Security alert: Label {label.id[:8]} was already received. Duplicate receipt prohibited.",
                    "ledger_updated": False,
                    "timestamp": now
                }

            if label.status != "DISPATCHED":
                return {
                    "success": False,
                    "scan_type": "RECEIVE",
                    "status": "INVALID_STATE",
                    "message": f"Package cannot be received because its current status is '{label.status}' (must be DISPATCHED).",
                    "ledger_updated": False,
                    "timestamp": now
                }

            # Receipt & Reconciliation Quantities
            recv_qty = accepted_quantity if accepted_quantity is not None else package.quantity
            dmg_qty = max(0, damaged_quantity)

            label.status = "RECEIVED"
            package.status = "RECEIVED" if dmg_qty == 0 else "RECONCILED_WITH_DAMAGE"
            transfer.status = "RECEIVED"
            transfer.received_at = now
            transfer.closed_at = now

            # Record ledger receipt at destination
            if recv_qty > 0:
                LedgerService.record_movement(
                    db=db,
                    facility_id=transfer.destination_facility_id,
                    batch_id=package.batch_id,
                    movement_type="TRANSFER_RECEIPT",
                    quantity_delta=recv_qty,
                    unit=package.unit,
                    reference_type="TRANSFER_RECEIPT",
                    reference_id=transfer.id,
                    actor_id=user_id,
                    idempotency_key=f"RECEIVE_{package.id}_{idempotency_key}",
                    reason=f"Verified QR receipt of package {package.package_reference} at destination"
                )

            # Record damage if any
            if dmg_qty > 0:
                LedgerService.record_movement(
                    db=db,
                    facility_id=transfer.destination_facility_id,
                    batch_id=package.batch_id,
                    movement_type="DAMAGE",
                    quantity_delta=0, # Damaged during transit not added to usable
                    unit=package.unit,
                    reference_type="TRANSIT_DAMAGE",
                    reference_id=transfer.id,
                    actor_id=user_id,
                    reason=f"Damage logged upon receipt: {dmg_qty} units"
                )

            scan_record = ScanEvent(
                serialized_label_id=label.id,
                transfer_id=transfer.id,
                facility_id=facility_id,
                user_id=user_id,
                scan_type="RECEIVE",
                result="SUCCESS",
                idempotency_key=idempotency_key,
                metadata_json={"accepted": recv_qty, "damaged": dmg_qty, "notes": notes}
            )
            db.add(scan_record)
            db.commit()

            return {
                "success": True,
                "scan_type": "RECEIVE",
                "status": "RECEIVED",
                "message": f"Package {package.package_reference} received and verified. Inventory ledger updated at destination.",
                "transfer_id": transfer.id,
                "package_id": package.id,
                "product_name": product.name,
                "lot_number": batch.manufacturer_lot_number,
                "expiry_date": str(batch.expiry_date),
                "verified_quantity": recv_qty,
                "ledger_updated": True,
                "timestamp": now
            }

        else:
            return {
                "success": False,
                "scan_type": scan_type,
                "status": "INVALID_SCAN_TYPE",
                "message": f"Unknown scan type '{scan_type}'. Must be DISPATCH or RECEIVE.",
                "ledger_updated": False,
                "timestamp": now
            }


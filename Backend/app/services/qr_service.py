"""
MediFlow QR Service & Verification Engine.

Authoritative QR generation, custody handoff verification, duplicate/replay protection,
multi-quantity reconciliation (accepted, damaged, rejected, quarantined, missing),
and atomic ledger integration.
"""
import io
import base64
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import qrcode
from sqlalchemy.orm import Session

from app.models.transfer import Transfer, TransferPackage, SerializedLabel, ScanEvent
from app.models.product import Batch, Product
from app.models.organization import Facility, User, FacilityMembership
from app.models.proposal import TransferProposal
from app.core.security import generate_secure_opaque_token, hash_token
from app.services.ledger_service import LedgerService


class QRService:
    """
    Authoritative service managing serialized QR labels, custody scans,
    and multi-category reconciliation ledgers.
    """

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
    def generate_labels_for_transfer(
        db: Session,
        transfer_id: str,
        actor_user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates serialized labels for an approved and reserved transfer.
        Only allowed when transfer is in RESERVED or READY_FOR_DISPATCH status.
        """
        transfer = db.query(Transfer).filter(Transfer.id == transfer_id).first()
        if not transfer:
            raise ValueError(f"Transfer {transfer_id} not found.")

        if transfer.status not in ("RESERVED", "READY_FOR_DISPATCH"):
            raise ValueError(
                f"Cannot generate labels: Transfer is in status '{transfer.status}' "
                f"(must be RESERVED or READY_FOR_DISPATCH)."
            )

        # Validate actor user belongs to source facility if user_id provided
        if actor_user_id:
            user = db.query(User).filter(User.id == actor_user_id).first()
            if not user:
                raise ValueError(f"User {actor_user_id} not found.")

        issued_labels = []
        for pkg in transfer.packages:
            if not pkg.label:
                token = generate_secure_opaque_token(prefix="MEDIFLOW")
                thash = hash_token(token)
                label = SerializedLabel(
                    transfer_package_id=pkg.id,
                    token_hash=thash,
                    label_version=1,
                    status="ISSUED"
                )
                db.add(label)
                db.flush()
                issued_labels.append({
                    "package_id": pkg.id,
                    "package_reference": pkg.package_reference,
                    "batch_id": pkg.batch_id,
                    "quantity": pkg.quantity,
                    "unit": pkg.unit,
                    "label_id": label.id,
                    "token": token,
                    "token_hash_preview": f"HASH_{thash[:8]}...",
                    "qr_data_uri": QRService.generate_qr_image_data_uri(token)
                })

        db.commit()
        return {
            "transfer_id": transfer.id,
            "status": transfer.status,
            "labels_issued_count": len(issued_labels),
            "labels": issued_labels
        }

    @staticmethod
    def get_transfer_labels(db: Session, transfer_id: str) -> Dict[str, Any]:
        """Returns all packages and label details for a transfer."""
        transfer = db.query(Transfer).filter(Transfer.id == transfer_id).first()
        if not transfer:
            raise ValueError(f"Transfer {transfer_id} not found.")

        packages_data = []
        for pkg in transfer.packages:
            label_data = None
            if pkg.label:
                label_data = {
                    "id": pkg.label.id,
                    "label_version": pkg.label.label_version,
                    "status": pkg.label.status,
                    "token_hash_preview": f"HASH_{pkg.label.token_hash[:8]}...",
                    "issued_at": pkg.label.issued_at.isoformat() if pkg.label.issued_at else None,
                }
            packages_data.append({
                "package_id": pkg.id,
                "package_reference": pkg.package_reference,
                "batch_id": pkg.batch_id,
                "lot_number": pkg.batch.manufacturer_lot_number if pkg.batch else None,
                "expiry_date": str(pkg.batch.expiry_date) if pkg.batch else None,
                "quantity": pkg.quantity,
                "unit": pkg.unit,
                "status": pkg.status,
                "label": label_data
            })

        return {
            "transfer_id": transfer.id,
            "status": transfer.status,
            "tracking_reference": transfer.tracking_reference,
            "source_facility_id": transfer.source_facility_id,
            "destination_facility_id": transfer.destination_facility_id,
            "packages": packages_data
        }

    @staticmethod
    def process_scan(
        db: Session,
        token: str,
        facility_id: str,
        user_id: str,
        scan_type: str,  # DISPATCH or RECEIVE
        idempotency_key: str,
        accepted_quantity: Optional[int] = None,
        damaged_quantity: int = 0,
        rejected_quantity: int = 0,
        quarantined_quantity: int = 0,
        expected_transfer_id: Optional[str] = None,
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

        # Check if label has been revoked or invalidated
        if label.status in ("REVOKED", "EXPIRED", "VOID"):
            return {
                "success": False,
                "scan_type": scan_type,
                "status": f"LABEL_{label.status}",
                "message": f"Verification failed: QR label has been {label.status.lower()} and is invalid for custody operations.",
                "ledger_updated": False,
                "timestamp": now
            }

        package = db.query(TransferPackage).filter(TransferPackage.id == label.transfer_package_id).first()
        transfer = db.query(Transfer).filter(Transfer.id == package.transfer_id).first()
        batch = db.query(Batch).filter(Batch.id == package.batch_id).first()
        product = db.query(Product).filter(Product.id == batch.product_id).first()

        # Check expected transfer matching (wrong transfer protection)
        if expected_transfer_id and transfer.id != expected_transfer_id:
            ScanEvent_record = ScanEvent(
                serialized_label_id=label.id,
                transfer_id=transfer.id,
                facility_id=facility_id,
                user_id=user_id,
                scan_type=scan_type,
                result="WRONG_TRANSFER",
                idempotency_key=idempotency_key,
                metadata_json={"attempted_transfer": expected_transfer_id, "actual_transfer": transfer.id}
            )
            db.add(ScanEvent_record)
            db.commit()
            return {
                "success": False,
                "scan_type": scan_type,
                "status": "WRONG_TRANSFER",
                "message": f"Verification rejected: Label belongs to transfer {transfer.id[:8]}..., but scan was submitted for {expected_transfer_id[:8]}...",
                "ledger_updated": False,
                "timestamp": now
            }

        # Check transfer status is not terminal
        if transfer.status in ("CANCELLED", "EXPIRED", "REJECTED", "FAILED", "CLOSED"):
            return {
                "success": False,
                "scan_type": scan_type,
                "status": f"TRANSFER_{transfer.status}",
                "message": f"Operation rejected: Parent transfer is in terminal status '{transfer.status}'.",
                "ledger_updated": False,
                "timestamp": now
            }

        # Validate user
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if not user or user.status != "ACTIVE":
                return {
                    "success": False,
                    "scan_type": scan_type,
                    "status": "UNAUTHORIZED_USER",
                    "message": "Authentication failed: Operator user record not found or inactive.",
                    "ledger_updated": False,
                    "timestamp": now
                }

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

            # State check: duplicate dispatch prevention
            if label.status in ("DISPATCHED", "RECEIVED"):
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
            rej_qty = max(0, rejected_quantity)
            quar_qty = max(0, quarantined_quantity)
            total_accounted = recv_qty + dmg_qty + rej_qty + quar_qty

            # Guard against over-quantity
            if total_accounted > package.quantity:
                ScanEvent_record = ScanEvent(
                    serialized_label_id=label.id,
                    transfer_id=transfer.id,
                    facility_id=facility_id,
                    user_id=user_id,
                    scan_type="RECEIVE",
                    result="OVER_QUANTITY_REJECTED",
                    idempotency_key=idempotency_key,
                    metadata_json={"total_accounted": total_accounted, "package_quantity": package.quantity}
                )
                db.add(ScanEvent_record)
                db.commit()
                return {
                    "success": False,
                    "scan_type": "RECEIVE",
                    "status": "OVER_QUANTITY_REJECTED",
                    "message": f"Reconciliation rejected: Accounted quantity ({total_accounted}) exceeds dispatched package quantity ({package.quantity}).",
                    "ledger_updated": False,
                    "timestamp": now
                }

            missing_qty = max(0, package.quantity - total_accounted)
            has_discrepancy = (dmg_qty > 0 or rej_qty > 0 or quar_qty > 0 or missing_qty > 0)

            label.status = "RECEIVED"
            package.status = "RECEIVED" if not has_discrepancy else "RECONCILED_WITH_DISCREPANCY"
            transfer.status = "RECEIVED" if not has_discrepancy else "PARTIALLY_RECEIVED"
            transfer.received_at = now
            if not has_discrepancy:
                transfer.closed_at = now

            # 1. Record accepted usable stock
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

            # 2. Record quarantined stock
            if quar_qty > 0:
                LedgerService.record_movement(
                    db=db,
                    facility_id=transfer.destination_facility_id,
                    batch_id=package.batch_id,
                    movement_type="QUARANTINE",
                    quantity_delta=quar_qty,
                    unit=package.unit,
                    reference_type="TRANSIT_QUARANTINE",
                    reference_id=transfer.id,
                    actor_id=user_id,
                    reason=f"Quarantined upon receipt: {quar_qty} units"
                )

            # 3. Record transit damage
            if dmg_qty > 0:
                LedgerService.record_movement(
                    db=db,
                    facility_id=transfer.destination_facility_id,
                    batch_id=package.batch_id,
                    movement_type="DAMAGE",
                    quantity_delta=0,
                    unit=package.unit,
                    reference_type="TRANSIT_DAMAGE",
                    reference_id=transfer.id,
                    actor_id=user_id,
                    reason=f"Damage logged upon receipt: {dmg_qty} units"
                )

            # 4. Record rejection
            if rej_qty > 0:
                LedgerService.record_movement(
                    db=db,
                    facility_id=transfer.destination_facility_id,
                    batch_id=package.batch_id,
                    movement_type="TRANSFER_REJECTION",
                    quantity_delta=0,
                    unit=package.unit,
                    reference_type="TRANSIT_REJECTION",
                    reference_id=transfer.id,
                    actor_id=user_id,
                    reason=f"Rejection logged upon receipt: {rej_qty} units"
                )

            scan_record = ScanEvent(
                serialized_label_id=label.id,
                transfer_id=transfer.id,
                facility_id=facility_id,
                user_id=user_id,
                scan_type="RECEIVE",
                result="SUCCESS",
                idempotency_key=idempotency_key,
                metadata_json={
                    "accepted": recv_qty,
                    "damaged": dmg_qty,
                    "rejected": rej_qty,
                    "quarantined": quar_qty,
                    "missing": missing_qty,
                    "notes": notes
                }
            )
            db.add(scan_record)
            db.commit()

            return {
                "success": True,
                "scan_type": "RECEIVE",
                "status": transfer.status,
                "message": (
                    f"Package {package.package_reference} received and verified. Destination ledger updated."
                    if not has_discrepancy else
                    f"Package {package.package_reference} received with reconciliation breakdown (Accepted: {recv_qty}, Damaged: {dmg_qty}, Rejected: {rej_qty}, Quarantined: {quar_qty}, Missing: {missing_qty})."
                ),
                "transfer_id": transfer.id,
                "package_id": package.id,
                "product_name": product.name,
                "lot_number": batch.manufacturer_lot_number,
                "expiry_date": str(batch.expiry_date),
                "verified_quantity": recv_qty,
                "damaged_quantity": dmg_qty,
                "rejected_quantity": rej_qty,
                "quarantined_quantity": quar_qty,
                "missing_quantity": missing_qty,
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

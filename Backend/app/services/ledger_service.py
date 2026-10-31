from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.inventory import InventoryLedger, FacilityBatchInventory
from app.models.audit import AuditEvent


class LedgerService:
    @staticmethod
    def record_movement(
        db: Session,
        facility_id: str,
        batch_id: str,
        movement_type: str,
        quantity_delta: int,
        unit: str = "UNIT",
        reference_type: Optional[str] = None,
        reference_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        reason: Optional[str] = None,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> InventoryLedger:
        """
        Atomically records an auditable ledger movement and updates the
        materialised FacilityBatchInventory projection.
        """
        if idempotency_key:
            existing = db.query(InventoryLedger).filter(
                InventoryLedger.idempotency_key == idempotency_key
            ).first()
            if existing:
                return existing

        import uuid
        entry_id = str(uuid.uuid4())
        ledger_entry = InventoryLedger(
            id=entry_id,
            facility_id=facility_id,
            batch_id=batch_id,
            movement_type=movement_type,
            quantity_delta=quantity_delta,
            unit=unit,
            reference_type=reference_type,
            reference_id=reference_id,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            reason=reason,
            metadata_json=metadata_json,
            occurred_at=datetime.now(timezone.utc)
        )
        db.add(ledger_entry)

        # Update materialised inventory projection
        inv = db.query(FacilityBatchInventory).filter(
            FacilityBatchInventory.facility_id == facility_id,
            FacilityBatchInventory.batch_id == batch_id
        ).with_for_update().first()

        if not inv:
            inv = FacilityBatchInventory(
                facility_id=facility_id,
                batch_id=batch_id,
                on_hand_quantity=max(0, quantity_delta),
                reserved_quantity=0,
                quarantined_quantity=0,
                damaged_quantity=0,
                unit=unit,
                version=1
            )
            db.add(inv)
            db.flush()  # Flush so subsequent calls find this record via query
        else:
            inv.version += 1
            inv.last_reconciled_at = datetime.now(timezone.utc)
            if movement_type in ("OPENING_BALANCE", "PURCHASE_RECEIPT", "TRANSFER_RECEIPT", "ADJUSTMENT_ADD"):
                inv.on_hand_quantity += quantity_delta
            elif movement_type in ("CONSUMPTION", "DAMAGE", "EXPIRY", "ADJUSTMENT_SUB"):
                inv.on_hand_quantity = max(0, inv.on_hand_quantity + quantity_delta) # quantity_delta is negative
            elif movement_type == "TRANSFER_DISPATCH":
                # Decrement on_hand and decrement reserved
                qty = abs(quantity_delta)
                inv.on_hand_quantity = max(0, inv.on_hand_quantity - qty)
                inv.reserved_quantity = max(0, inv.reserved_quantity - qty)
            elif movement_type == "TRANSFER_RESERVATION":
                inv.reserved_quantity += abs(quantity_delta)
            elif movement_type == "TRANSFER_RESERVATION_RELEASE":
                inv.reserved_quantity = max(0, inv.reserved_quantity - abs(quantity_delta))
            elif movement_type == "QUARANTINE":
                inv.quarantined_quantity += abs(quantity_delta)
            elif movement_type == "RELEASE_FROM_QUARANTINE":
                inv.quarantined_quantity = max(0, inv.quarantined_quantity - abs(quantity_delta))

        # Record audit trail
        audit = AuditEvent(
            facility_id=facility_id,
            actor_id=actor_id,
            action=f"LEDGER_{movement_type}",
            entity_type="INVENTORY_LEDGER",
            entity_id=ledger_entry.id,
            before_state=None,
            after_state={"quantity_delta": quantity_delta, "unit": unit},
            reason=reason
        )
        db.add(audit)

        return ledger_entry

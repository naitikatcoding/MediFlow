import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.inventory import InventoryLedger, FacilityBatchInventory
from app.models.product import Batch, Product
from app.models.organization import Facility
from app.models.audit import AuditEvent


class LedgerService:
    VALID_MOVEMENT_TYPES = {
        "OPENING_BALANCE",
        "PURCHASE_RECEIPT",
        "CONSUMPTION",
        "TRANSFER_RESERVATION",
        "TRANSFER_RESERVATION_RELEASE",
        "TRANSFER_DISPATCH",
        "TRANSFER_RECEIPT",
        "TRANSFER_REJECTION",
        "DAMAGE",
        "EXPIRY",
        "RETURN",
        "ADJUSTMENT",
        "QUARANTINE",
        "RELEASE_FROM_QUARANTINE",
    }

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
        Atomically records an auditable, immutable ledger movement and updates the
        materialised FacilityBatchInventory projection.
        Enforces non-negative stock invariants, unit checks, and idempotency.
        """
        if movement_type not in LedgerService.VALID_MOVEMENT_TYPES:
            raise ValueError(f"Invalid movement type: {movement_type}. Must be one of {LedgerService.VALID_MOVEMENT_TYPES}")

        # Idempotency check: if key exists, return existing record without reapplying delta
        if idempotency_key:
            existing = db.query(InventoryLedger).filter(
                InventoryLedger.idempotency_key == idempotency_key
            ).first()
            if existing:
                return existing

        # Validate facility exists
        fac = db.query(Facility).filter(Facility.id == facility_id).first()
        if not fac:
            raise ValueError(f"Facility '{facility_id}' not found.")

        # Validate batch exists
        batch = db.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            raise ValueError(f"Batch '{batch_id}' not found.")

        # Fetch product to validate base unit if available
        product = db.query(Product).filter(Product.id == batch.product_id).first()
        if product and product.base_unit and unit != "UNIT" and product.base_unit != "UNIT":
            if unit.upper() != product.base_unit.upper():
                raise ValueError(
                    f"Unit mismatch: item requires '{product.base_unit}', received '{unit}'."
                )

        # Lock materialised projection row
        inv = db.query(FacilityBatchInventory).filter(
            FacilityBatchInventory.facility_id == facility_id,
            FacilityBatchInventory.batch_id == batch_id
        ).with_for_update().first()

        current_on_hand = inv.on_hand_quantity if inv else 0
        current_reserved = inv.reserved_quantity if inv else 0
        current_quarantined = inv.quarantined_quantity if inv else 0
        current_damaged = inv.damaged_quantity if inv else 0
        current_usable = max(0, current_on_hand - current_reserved - current_quarantined - current_damaged)

        before_state = {
            "on_hand": current_on_hand,
            "reserved": current_reserved,
            "quarantined": current_quarantined,
            "damaged": current_damaged,
            "usable": current_usable,
            "unit": inv.unit if inv else unit
        }

        # Calculate proposed new states based on movement type
        qty = abs(quantity_delta)
        new_on_hand = current_on_hand
        new_reserved = current_reserved
        new_quarantined = current_quarantined
        new_damaged = current_damaged

        if movement_type in ("OPENING_BALANCE", "PURCHASE_RECEIPT", "TRANSFER_RECEIPT", "RETURN"):
            new_on_hand += qty
        elif movement_type == "CONSUMPTION":
            new_on_hand -= qty
        elif movement_type == "ADJUSTMENT":
            new_on_hand += quantity_delta  # can be positive or negative
        elif movement_type == "TRANSFER_RESERVATION":
            new_reserved += qty
        elif movement_type == "TRANSFER_RESERVATION_RELEASE":
            new_reserved -= qty
        elif movement_type == "TRANSFER_DISPATCH":
            new_on_hand -= qty
            new_reserved -= qty
        elif movement_type == "TRANSFER_REJECTION":
            # Released from reservation and placed into quarantine or written off
            new_reserved -= qty
            new_quarantined += qty
        elif movement_type == "DAMAGE":
            new_damaged += qty
        elif movement_type == "EXPIRY":
            new_quarantined += qty
        elif movement_type == "QUARANTINE":
            new_quarantined += qty
        elif movement_type == "RELEASE_FROM_QUARANTINE":
            new_quarantined -= qty

        new_usable = new_on_hand - new_reserved - new_quarantined - new_damaged

        # Invariant checks: reject negative quantities or reserved exceeding on_hand
        if new_on_hand < 0:
            raise ValueError(
                f"Negative stock invariant: on_hand would become {new_on_hand} (current: {current_on_hand}, delta: {quantity_delta})."
            )
        if new_reserved < 0:
            raise ValueError(
                f"Negative reservation invariant: reserved would become {new_reserved}."
            )
        if new_quarantined < 0:
            raise ValueError(
                f"Negative quarantine invariant: quarantined would become {new_quarantined}."
            )
        if new_damaged < 0:
            raise ValueError(
                f"Negative damaged invariant: damaged would become {new_damaged}."
            )
        if new_reserved > new_on_hand:
            raise ValueError(
                f"Reservation invariant: reserved ({new_reserved}) cannot exceed on_hand ({new_on_hand})."
            )
        if new_usable < 0:
            raise ValueError(
                f"Usable stock invariant: available usable stock would become {new_usable} (cannot be negative)."
            )

        now = datetime.now(timezone.utc)
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
            actor_id=actor_id or "system",
            idempotency_key=idempotency_key,
            reason=reason or f"Movement: {movement_type}",
            metadata_json=metadata_json,
            occurred_at=now,
            created_at=now
        )
        db.add(ledger_entry)

        # Update or create materialized projection
        if not inv:
            inv = FacilityBatchInventory(
                facility_id=facility_id,
                batch_id=batch_id,
                on_hand_quantity=new_on_hand,
                reserved_quantity=new_reserved,
                quarantined_quantity=new_quarantined,
                damaged_quantity=new_damaged,
                unit=unit,
                last_reconciled_at=now,
                version=1
            )
            db.add(inv)
            db.flush()
        else:
            inv.on_hand_quantity = new_on_hand
            inv.reserved_quantity = new_reserved
            inv.quarantined_quantity = new_quarantined
            inv.damaged_quantity = new_damaged
            inv.last_reconciled_at = now
            inv.version += 1

        after_state = {
            "on_hand": new_on_hand,
            "reserved": new_reserved,
            "quarantined": new_quarantined,
            "damaged": new_damaged,
            "usable": new_usable,
            "unit": unit
        }

        # Record audit event
        audit = AuditEvent(
            facility_id=facility_id,
            actor_id=actor_id or "system",
            action=f"INVENTORY_{movement_type}",
            entity_type="INVENTORY_LEDGER",
            entity_id=ledger_entry.id,
            before_state=before_state,
            after_state=after_state,
            reason=reason
        )
        db.add(audit)

        return ledger_entry

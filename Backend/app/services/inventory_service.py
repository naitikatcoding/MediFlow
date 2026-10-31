from datetime import datetime, timezone, date, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.inventory import FacilityBatchInventory, InventoryLedger
from app.models.product import Product, Batch
from app.models.organization import Facility


class InventoryService:
    @staticmethod
    def get_data_freshness_status(dt: Optional[datetime]) -> str:
        if not dt:
            return "STALE"
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = now - dt
        if diff < timedelta(hours=24):
            return "FRESH"
        elif diff < timedelta(hours=72):
            return "STALE"
        return "CRITICALLY_STALE"

    @staticmethod
    def get_facility_inventory(
        db: Session,
        facility_id: Optional[str] = None,
        product_id: Optional[str] = None,
        storage: Optional[str] = None,
        near_expiry_days: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Facility-scoped inventory list with lot-level details, FEFO order, and block status."""
        query = db.query(
            FacilityBatchInventory, Batch, Product, Facility
        ).join(
            Batch, FacilityBatchInventory.batch_id == Batch.id
        ).join(
            Product, Batch.product_id == Product.id
        ).join(
            Facility, FacilityBatchInventory.facility_id == Facility.id
        )

        if facility_id:
            query = query.filter(FacilityBatchInventory.facility_id == facility_id)
        if product_id:
            query = query.filter(Batch.product_id == product_id)
        if storage:
            query = query.filter(Product.storage_requirements == storage)

        results = query.order_by(Batch.expiry_date.asc()).all()
        today = date.today()

        inventory_list = []
        for inv, batch, product, facility in results:
            usable = max(0, inv.on_hand_quantity - inv.reserved_quantity - inv.quarantined_quantity - inv.damaged_quantity)
            days_to_expiry = (batch.expiry_date - today).days

            if near_expiry_days is not None and days_to_expiry > near_expiry_days:
                continue

            # Blocking conditions
            blocking_reasons = []
            if days_to_expiry <= 0:
                blocking_reasons.append("EXPIRED")
            if batch.quality_status != "RELEASED":
                blocking_reasons.append(f"QUALITY_STATUS_{batch.quality_status}")
            if inv.quarantined_quantity > 0:
                blocking_reasons.append("QUARANTINED_QUANTITY_PRESENT")
            if inv.damaged_quantity > 0:
                blocking_reasons.append("DAMAGED_QUANTITY_PRESENT")

            is_blocked = len(blocking_reasons) > 0
            freshness = InventoryService.get_data_freshness_status(inv.last_reconciled_at)

            inventory_list.append({
                "id": inv.id,
                "facility_id": inv.facility_id,
                "facility_name": facility.name,
                "batch_id": batch.id,
                "product_id": product.id,
                "product_name": product.name,
                "generic_name": product.generic_name,
                "strength": product.strength,
                "dosage_form": product.dosage_form,
                "storage_requirements": product.storage_requirements,
                "manufacturer_lot_number": batch.manufacturer_lot_number,
                "expiry_date": batch.expiry_date,
                "days_to_expiry": days_to_expiry,
                "on_hand_quantity": inv.on_hand_quantity,
                "reserved_quantity": inv.reserved_quantity,
                "quarantined_quantity": inv.quarantined_quantity,
                "damaged_quantity": inv.damaged_quantity,
                "usable_quantity": usable,
                "unit": inv.unit,
                "quality_status": batch.quality_status,
                "is_blocked": is_blocked,
                "blocking_reasons": blocking_reasons,
                "data_freshness_status": freshness,
                "last_reconciled_at": inv.last_reconciled_at
            })

        return inventory_list

    @staticmethod
    def get_inventory_summary(db: Session, facility_id: Optional[str] = None) -> Dict[str, Any]:
        """Calculates aggregated inventory summary for network or a specific facility."""
        items = InventoryService.get_facility_inventory(db, facility_id=facility_id)

        total_on_hand = sum(item["on_hand_quantity"] for item in items)
        total_reserved = sum(item["reserved_quantity"] for item in items)
        total_quarantined = sum(item["quarantined_quantity"] for item in items)
        total_damaged = sum(item["damaged_quantity"] for item in items)
        total_usable = sum(item["usable_quantity"] for item in items)

        distinct_products = len(set(item["product_id"] for item in items))
        distinct_batches = len(set(item["batch_id"] for item in items))
        near_expiry_count = sum(1 for item in items if item["days_to_expiry"] <= 45)
        cold_chain_count = sum(1 for item in items if item["storage_requirements"] == "COLD_CHAIN_2_8C")

        freshness_states = [item["data_freshness_status"] for item in items]
        if "CRITICALLY_STALE" in freshness_states:
            overall_freshness = "CRITICALLY_STALE"
        elif "STALE" in freshness_states:
            overall_freshness = "STALE"
        else:
            overall_freshness = "FRESH"

        latest_update = max((item["last_reconciled_at"] for item in items if item["last_reconciled_at"]), default=None)

        return {
            "facility_id": facility_id,
            "total_on_hand": total_on_hand,
            "total_reserved": total_reserved,
            "total_quarantined": total_quarantined,
            "total_damaged": total_damaged,
            "total_usable": total_usable,
            "distinct_products_count": distinct_products,
            "distinct_batches_count": distinct_batches,
            "near_expiry_batches_count": near_expiry_count,
            "cold_chain_items_count": cold_chain_count,
            "data_freshness_status": overall_freshness,
            "last_updated_at": latest_update
        }

    @staticmethod
    def get_product_stock_summary(db: Session, facility_id: str, product_id: str) -> Dict[str, Any]:
        """Calculates total usable, reserved, and batches for a product at a facility."""
        items = InventoryService.get_facility_inventory(db, facility_id=facility_id, product_id=product_id)
        total_on_hand = sum(item["on_hand_quantity"] for item in items)
        total_reserved = sum(item["reserved_quantity"] for item in items)
        total_quarantined = sum(item["quarantined_quantity"] for item in items)
        total_damaged = sum(item["damaged_quantity"] for item in items)
        total_usable = sum(item["usable_quantity"] for item in items)

        return {
            "facility_id": facility_id,
            "product_id": product_id,
            "total_on_hand": total_on_hand,
            "total_reserved": total_reserved,
            "total_quarantined": total_quarantined,
            "total_damaged": total_damaged,
            "total_usable": total_usable,
            "batches": items
        }

    @staticmethod
    def get_facility_product_detail(db: Session, facility_id: str, product_id: str) -> Optional[Dict[str, Any]]:
        """Detailed breakdown for a product at a specific facility."""
        product = db.query(Product).filter(Product.id == product_id).first()
        facility = db.query(Facility).filter(Facility.id == facility_id).first()
        if not product or not facility:
            return None

        batches = InventoryService.get_facility_inventory(db, facility_id=facility_id, product_id=product_id)

        total_on_hand = sum(b["on_hand_quantity"] for b in batches)
        total_reserved = sum(b["reserved_quantity"] for b in batches)
        total_quarantined = sum(b["quarantined_quantity"] for b in batches)
        total_damaged = sum(b["damaged_quantity"] for b in batches)
        total_usable = sum(b["usable_quantity"] for b in batches)

        freshness = "FRESH"
        if batches:
            freshness = batches[0]["data_freshness_status"]

        return {
            "facility_id": facility.id,
            "facility_name": facility.name,
            "product_id": product.id,
            "product_name": product.name,
            "generic_name": product.generic_name,
            "strength": product.strength,
            "dosage_form": product.dosage_form,
            "base_unit": product.base_unit,
            "storage_requirements": product.storage_requirements,
            "total_on_hand": total_on_hand,
            "total_reserved": total_reserved,
            "total_quarantined": total_quarantined,
            "total_damaged": total_damaged,
            "total_usable": total_usable,
            "data_freshness_status": freshness,
            "batches": batches
        }

    @staticmethod
    def check_batch_eligibility(
        db: Session,
        batch_id: str,
        destination_facility_id: Optional[str] = None,
        min_shelf_life_days: int = 15
    ) -> Dict[str, Any]:
        """
        Validates batch eligibility for transfer:
        Blocks if expired, quarantined, damaged, recalled, missing data, shelf-life insufficient,
        or incompatible with destination storage capabilities.
        """
        batch = db.query(Batch).filter(Batch.id == batch_id).first()
        if not batch:
            return {
                "batch_id": batch_id,
                "is_eligible": False,
                "is_blocked": True,
                "blocking_reasons": ["BATCH_NOT_FOUND"],
                "days_to_expiry": 0,
                "remaining_shelf_life_days": 0,
                "storage_compatible": False
            }

        product = db.query(Product).filter(Product.id == batch.product_id).first()
        today = date.today()
        days_to_expiry = (batch.expiry_date - today).days

        blocking_reasons = []

        if days_to_expiry <= 0:
            blocking_reasons.append("EXPIRED")
        elif days_to_expiry < min_shelf_life_days:
            blocking_reasons.append(f"INSUFFICIENT_SHELF_LIFE_{days_to_expiry}_DAYS_LESS_THAN_{min_shelf_life_days}")

        if batch.quality_status == "RECALLED":
            blocking_reasons.append("BATCH_RECALLED")
        elif batch.quality_status == "QUARANTINED":
            blocking_reasons.append("BATCH_QUARANTINED")
        elif batch.quality_status == "DAMAGED":
            blocking_reasons.append("BATCH_DAMAGED")
        elif batch.quality_status != "RELEASED":
            blocking_reasons.append(f"QUALITY_STATUS_{batch.quality_status}")

        if not batch.manufacturer_lot_number or not batch.manufacturer:
            blocking_reasons.append("MISSING_MANDATORY_BATCH_DATA")

        # Storage compatibility with destination
        storage_compatible = True
        if destination_facility_id and product:
            dest = db.query(Facility).filter(Facility.id == destination_facility_id).first()
            if dest and product.storage_requirements == "COLD_CHAIN_2_8C":
                dest_caps = dest.storage_capabilities or {}
                if not dest_caps.get("cold_chain", False):
                    storage_compatible = False
                    blocking_reasons.append("DESTINATION_STORAGE_INCOMPATIBLE_COLD_CHAIN_MISSING")

        is_blocked = len(blocking_reasons) > 0

        return {
            "batch_id": batch.id,
            "is_eligible": not is_blocked,
            "is_blocked": is_blocked,
            "blocking_reasons": blocking_reasons,
            "days_to_expiry": days_to_expiry,
            "remaining_shelf_life_days": days_to_expiry,
            "storage_compatible": storage_compatible
        }

    @staticmethod
    def allocate_fefo(
        db: Session,
        facility_id: str,
        product_id: str,
        requested_quantity: int,
        destination_facility_id: Optional[str] = None,
        min_shelf_life_days: int = 15
    ) -> Dict[str, Any]:
        """
        FEFO (First Expiry, First Out) batch allocation helper.
        Allocates usable eligible stock ordered strictly by ascending expiry date.
        Filters out blocked, expired, quarantined, and storage-incompatible batches.
        """
        if requested_quantity <= 0:
            return {
                "facility_id": facility_id,
                "product_id": product_id,
                "requested_quantity": requested_quantity,
                "allocated_total": 0,
                "unallocated_deficit": 0,
                "is_fully_allocated": True,
                "allocations": []
            }

        batches = InventoryService.get_facility_inventory(
            db, facility_id=facility_id, product_id=product_id
        )

        # Sort strictly by expiry_date ascending (FEFO)
        batches.sort(key=lambda b: b["expiry_date"])

        allocated_items = []
        remaining_needed = requested_quantity

        for b in batches:
            if remaining_needed <= 0:
                break

            # Eligibility check
            check = InventoryService.check_batch_eligibility(
                db,
                batch_id=b["batch_id"],
                destination_facility_id=destination_facility_id,
                min_shelf_life_days=min_shelf_life_days
            )
            if not check["is_eligible"]:
                continue

            usable = b["usable_quantity"]
            if usable <= 0:
                continue

            alloc_qty = min(usable, remaining_needed)
            allocated_items.append({
                "batch_id": b["batch_id"],
                "manufacturer_lot_number": b["manufacturer_lot_number"],
                "expiry_date": b["expiry_date"],
                "days_to_expiry": b["days_to_expiry"],
                "allocated_quantity": alloc_qty,
                "unit": b["unit"]
            })
            remaining_needed -= alloc_qty

        allocated_total = requested_quantity - remaining_needed

        return {
            "facility_id": facility_id,
            "product_id": product_id,
            "requested_quantity": requested_quantity,
            "allocated_total": allocated_total,
            "unallocated_deficit": remaining_needed,
            "is_fully_allocated": remaining_needed == 0,
            "allocations": allocated_items
        }

    @staticmethod
    def reconcile_batch_with_ledger(db: Session, facility_id: str, batch_id: str) -> Dict[str, Any]:
        """
        Reconciles materialised projection with the sum of immutable ledger entries.
        Reports balance discrepancies and timestamps reconciliation.
        """
        inv = db.query(FacilityBatchInventory).filter(
            FacilityBatchInventory.facility_id == facility_id,
            FacilityBatchInventory.batch_id == batch_id
        ).first()

        batch = db.query(Batch).filter(Batch.id == batch_id).first()
        product = db.query(Product).filter(Product.id == batch.product_id).first() if batch else None

        entries = db.query(InventoryLedger).filter(
            InventoryLedger.facility_id == facility_id,
            InventoryLedger.batch_id == batch_id
        ).all()

        computed_on_hand = 0
        for e in entries:
            mtype = e.movement_type
            qty = abs(e.quantity_delta)
            if mtype in ("OPENING_BALANCE", "PURCHASE_RECEIPT", "TRANSFER_RECEIPT", "RETURN"):
                computed_on_hand += qty
            elif mtype in ("CONSUMPTION", "TRANSFER_DISPATCH"):
                computed_on_hand -= qty
            elif mtype == "ADJUSTMENT":
                computed_on_hand += e.quantity_delta

        materialized_on_hand = inv.on_hand_quantity if inv else 0
        discrepancy = materialized_on_hand - computed_on_hand
        now = datetime.now(timezone.utc)

        if inv:
            inv.last_reconciled_at = now
            db.commit()

        return {
            "facility_id": facility_id,
            "batch_id": batch_id,
            "product_name": product.name if product else None,
            "lot_number": batch.manufacturer_lot_number if batch else None,
            "materialized_on_hand": materialized_on_hand,
            "ledger_computed_on_hand": computed_on_hand,
            "discrepancy": discrepancy,
            "is_balanced": discrepancy == 0,
            "last_reconciled_at": now
        }

    @staticmethod
    def reconcile_facility(db: Session, facility_id: str) -> Dict[str, Any]:
        """Reconciles all inventory records at a facility against the movement ledger."""
        inv_list = db.query(FacilityBatchInventory).filter(
            FacilityBatchInventory.facility_id == facility_id
        ).all()

        results = []
        balanced_count = 0
        discrepancy_count = 0

        for inv in inv_list:
            res = InventoryService.reconcile_batch_with_ledger(db, facility_id, inv.batch_id)
            results.append(res)
            if res["is_balanced"]:
                balanced_count += 1
            else:
                discrepancy_count += 1

        return {
            "facility_id": facility_id,
            "reconciled_batches_count": len(results),
            "balanced_batches_count": balanced_count,
            "discrepancy_count": discrepancy_count,
            "results": results
        }

from datetime import datetime, timezone, date
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.inventory import FacilityBatchInventory
from app.models.product import Product, Batch
from app.models.organization import Facility


class InventoryService:
    @staticmethod
    def get_facility_inventory(
        db: Session,
        facility_id: Optional[str] = None,
        product_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
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

        results = query.order_by(Batch.expiry_date.asc()).all()
        today = date.today()

        inventory_list = []
        for inv, batch, product, facility in results:
            usable = max(0, inv.on_hand_quantity - inv.reserved_quantity - inv.quarantined_quantity - inv.damaged_quantity)
            days_to_expiry = (batch.expiry_date - today).days

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
                "last_reconciled_at": inv.last_reconciled_at
            })

        return inventory_list

    @staticmethod
    def get_product_stock_summary(db: Session, facility_id: str, product_id: str) -> Dict[str, Any]:
        """Calculates total usable, reserved, and batches for a product at a facility."""
        items = InventoryService.get_facility_inventory(db, facility_id=facility_id, product_id=product_id)
        total_on_hand = sum(item["on_hand_quantity"] for item in items)
        total_reserved = sum(item["reserved_quantity"] for item in items)
        total_usable = sum(item["usable_quantity"] for item in items)

        return {
            "facility_id": facility_id,
            "product_id": product_id,
            "total_on_hand": total_on_hand,
            "total_reserved": total_reserved,
            "total_usable": total_usable,
            "batches": items
        }


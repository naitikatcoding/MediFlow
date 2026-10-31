from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.proposal import TransferProposal, TransferProposalBatch, TransferApproval
from app.models.transfer import Transfer, TransferPackage, SerializedLabel
from app.models.inventory import FacilityBatchInventory
from app.models.audit import AuditEvent
from app.core.security import generate_secure_opaque_token, hash_token
from app.services.ledger_service import LedgerService


class ProposalService:
    @staticmethod
    def create_proposal(
        db: Session,
        source_facility_id: str,
        destination_facility_id: str,
        product_id: str,
        proposed_quantity: int,
        batches: List[Dict[str, Any]],
        source_rationale: Dict[str, Any],
        destination_rationale: Dict[str, Any],
        priority: str = "MEDIUM",
        unit: str = "UNIT",
        optimisation_metadata: Optional[Dict[str, Any]] = None,
        workflow_id: Optional[str] = None
    ) -> TransferProposal:
        proposal = TransferProposal(
            source_facility_id=source_facility_id,
            destination_facility_id=destination_facility_id,
            product_id=product_id,
            proposed_quantity=proposed_quantity,
            unit=unit,
            status="PROPOSED",
            priority=priority,
            source_rationale=source_rationale,
            destination_rationale=destination_rationale,
            optimisation_metadata=optimisation_metadata,
            proposal_version=1,
            created_by_workflow_id=workflow_id
        )
        db.add(proposal)
        db.flush()

        for b in batches:
            pb = TransferProposalBatch(
                proposal_id=proposal.id,
                batch_id=b["batch_id"],
                quantity=b["quantity"],
                unit=b.get("unit", unit)
            )
            db.add(pb)

        audit = AuditEvent(
            facility_id=source_facility_id,
            action="CREATE_TRANSFER_PROPOSAL",
            entity_type="TRANSFER_PROPOSAL",
            entity_id=proposal.id,
            after_state={"proposed_quantity": proposed_quantity, "status": "PROPOSED"},
            reason="Automated matching identified safe redistribution opportunity"
        )
        db.add(audit)
        db.commit()
        db.refresh(proposal)
        return proposal

    @staticmethod
    def record_approval(
        db: Session,
        proposal_id: str,
        facility_id: str,
        approver_user_id: str,
        proposal_version: int,
        decision: str = "APPROVED",
        reason: Optional[str] = None,
        auto_reserve: bool = True
    ) -> Dict[str, Any]:
        """
        Records human approval for source or destination facility.
        Validates proposal version. If both parties have approved, triggers atomic stock reservation.
        """
        proposal = db.query(TransferProposal).filter(TransferProposal.id == proposal_id).first()
        if not proposal:
            raise ValueError(f"Transfer proposal {proposal_id} not found.")

        if proposal.proposal_version != proposal_version:
            raise ValueError(
                f"Version mismatch: Proposal is at version {proposal.proposal_version}, but approval was for version {proposal_version}."
            )

        if facility_id not in (proposal.source_facility_id, proposal.destination_facility_id):
            raise ValueError(f"Facility {facility_id} is neither the source nor destination of this proposal.")

        if decision == "REJECTED":
            proposal.status = "REJECTED"
            db.commit()
            return {"status": "REJECTED", "message": f"Proposal rejected by facility {facility_id}."}

        # Check if already approved by this facility for this version
        existing_appr = db.query(TransferApproval).filter(
            TransferApproval.proposal_id == proposal_id,
            TransferApproval.facility_id == facility_id,
            TransferApproval.proposal_version == proposal_version
        ).first()

        if not existing_appr:
            approval = TransferApproval(
                proposal_id=proposal_id,
                proposal_version=proposal_version,
                facility_id=facility_id,
                approver_user_id=approver_user_id,
                decision=decision,
                reason=reason or "Clinical and operational approval confirmed"
            )
            db.add(approval)
            db.flush()

        # Check if both facilities have approved
        approvals = db.query(TransferApproval).filter(
            TransferApproval.proposal_id == proposal_id,
            TransferApproval.proposal_version == proposal_version,
            TransferApproval.decision == "APPROVED"
        ).all()

        approved_facility_ids = {a.facility_id for a in approvals}
        has_source = proposal.source_facility_id in approved_facility_ids
        has_dest = proposal.destination_facility_id in approved_facility_ids

        if has_source and not has_dest:
            proposal.status = "PENDING_DESTINATION_APPROVAL"
            db.commit()
            return {
                "status": proposal.status,
                "message": "Source facility approved. Awaiting destination facility approval.",
                "source_approved": True,
                "destination_approved": False,
                "reserved": False
            }
        elif has_dest and not has_source:
            proposal.status = "PENDING_SOURCE_APPROVAL"
            db.commit()
            return {
                "status": proposal.status,
                "message": "Destination facility accepted. Awaiting source facility approval.",
                "source_approved": False,
                "destination_approved": True,
                "reserved": False
            }
        elif has_source and has_dest:
            proposal.status = "APPROVED"
            if auto_reserve:
                # Concurrency-safe atomic reservation
                reservation_result = ProposalService.reserve_stock_and_issue_labels(db, proposal)
                return reservation_result
            else:
                db.commit()
                return {
                    "status": "APPROVED",
                    "source_approved": True,
                    "destination_approved": True,
                    "reserved": False,
                    "message": "Both facilities approved. Ready for workflow resumption."
                }

        db.commit()
        return {"status": proposal.status, "source_approved": has_source, "destination_approved": has_dest}

    @staticmethod
    def reserve_stock_and_issue_labels(db: Session, proposal: TransferProposal) -> Dict[str, Any]:
        """
        Concurrency-safe reservation transaction:
        Re-validates stock availability under row lock.
        If stock changed or is insufficient -> aborts cleanly, records failure.
        If sufficient -> reserves inventory, creates Transfer, packages, and serialized QR labels.
        """
        # Check if already reserved
        existing_transfer = db.query(Transfer).filter(Transfer.proposal_id == proposal.id).first()
        if existing_transfer:
            return {
                "status": "RESERVED",
                "success": True,
                "transfer_id": existing_transfer.id,
                "proposal_id": proposal.id,
                "message": "Transfer already reserved."
            }

        proposal_batches = db.query(TransferProposalBatch).filter(
            TransferProposalBatch.proposal_id == proposal.id
        ).all()

        # Revalidate under row-lock
        for pb in proposal_batches:
            inv = db.query(FacilityBatchInventory).filter(
                FacilityBatchInventory.facility_id == proposal.source_facility_id,
                FacilityBatchInventory.batch_id == pb.batch_id
            ).with_for_update().first()

            if not inv or inv.usable_quantity < pb.quantity:
                proposal.status = "FAILED_INSUFFICIENT_STOCK"
                db.commit()
                return {
                    "status": "FAILED_INSUFFICIENT_STOCK",
                    "success": False,
                    "message": f"Reservation failed: Source inventory changed before reservation. Batch {pb.batch_id} has {inv.usable_quantity if inv else 0} usable units, required {pb.quantity}. Safe replanning triggered."
                }

        # If all batches verified, reserve stock
        for pb in proposal_batches:
            LedgerService.record_movement(
                db=db,
                facility_id=proposal.source_facility_id,
                batch_id=pb.batch_id,
                movement_type="TRANSFER_RESERVATION",
                quantity_delta=pb.quantity,
                unit=pb.unit,
                reference_type="TRANSFER_PROPOSAL",
                reference_id=proposal.id,
                reason=f"Stock reservation for approved transfer proposal {proposal.id}"
            )

        # Create physical Transfer record
        transfer = Transfer(
            proposal_id=proposal.id,
            status="RESERVED",
            source_facility_id=proposal.source_facility_id,
            destination_facility_id=proposal.destination_facility_id,
            tracking_reference=f"TRK-SOS-{proposal.id[:8].upper()}"
        )
        db.add(transfer)
        db.flush()

        # Create packages and serialized labels
        pkg_counter = 1
        issued_labels = []
        for pb in proposal_batches:
            pkg = TransferPackage(
                transfer_id=transfer.id,
                package_reference=f"PKG-{pkg_counter:03d}",
                batch_id=pb.batch_id,
                quantity=pb.quantity,
                unit=pb.unit,
                status="PREPARED"
            )
            db.add(pkg)
            db.flush()

            # Issue opaque random token and store hash
            token = generate_secure_opaque_token(prefix=f"SOS_{transfer.id[:6].upper()}")
            thash = hash_token(token)

            label = SerializedLabel(
                transfer_package_id=pkg.id,
                token_hash=thash,
                label_version=1,
                status="ISSUED"
            )
            db.add(label)
            issued_labels.append({
                "package_id": pkg.id,
                "package_reference": pkg.package_reference,
                "token": token,
                "token_hash": thash,
                "quantity": pb.quantity
            })
            pkg_counter += 1

        proposal.status = "RESERVED"
        transfer.status = "READY_FOR_DISPATCH"

        audit = AuditEvent(
            facility_id=proposal.source_facility_id,
            action="RESERVE_TRANSFER_STOCK",
            entity_type="TRANSFER",
            entity_id=transfer.id,
            after_state={"transfer_status": "READY_FOR_DISPATCH", "packages_created": len(issued_labels)},
            reason="Dual human approval obtained; stock reserved in database"
        )
        db.add(audit)
        db.commit()

        return {
            "status": "RESERVED",
            "success": True,
            "transfer_id": transfer.id,
            "message": f"Dual approval confirmed. {proposal.proposed_quantity} units reserved. Transfer {transfer.id} ready for dispatch.",
            "labels": issued_labels,
            "source_approved": True,
            "destination_approved": True
        }


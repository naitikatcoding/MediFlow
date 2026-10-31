"""
MediFlow Transfer State Machine & Governance Service.
Implements authoritative state transition validation, dual-facility approval with
role/membership enforcement, concurrency-safe reservation with row locking,
cancellation/expiry with exactly-once compensating ledger entries, and re-planning.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.models.proposal import TransferProposal, TransferProposalBatch, TransferApproval
from app.models.transfer import Transfer, TransferPackage, SerializedLabel
from app.models.inventory import FacilityBatchInventory
from app.models.organization import Facility, User, FacilityMembership
from app.models.product import Batch
from app.models.audit import AuditEvent
from app.core.security import generate_secure_opaque_token, hash_token
from app.services.ledger_service import LedgerService

logger = logging.getLogger("mediflow.transfer")

# ---------------------------------------------------------------------------
# State machine constants
# ---------------------------------------------------------------------------

ALLOWED_TRANSFER_TRANSITIONS: Set[Tuple[str, str]] = {
    ("RESERVED", "READY_FOR_DISPATCH"),
    ("READY_FOR_DISPATCH", "DISPATCHED"),
    ("DISPATCHED", "IN_TRANSIT"),
    ("IN_TRANSIT", "RECEIVED_PENDING_VERIFICATION"),
    ("RECEIVED_PENDING_VERIFICATION", "PARTIALLY_RECEIVED"),
    ("RECEIVED_PENDING_VERIFICATION", "RECEIVED"),
    ("RECEIVED_PENDING_VERIFICATION", "RECONCILIATION_REQUIRED"),
    ("PARTIALLY_RECEIVED", "RECONCILIATION_REQUIRED"),
    ("PARTIALLY_RECEIVED", "RECEIVED"),
    ("RECONCILIATION_REQUIRED", "RECEIVED"),
    ("RECONCILIATION_REQUIRED", "CLOSED"),
    ("RECEIVED", "CLOSED"),
    ("RESERVED", "CANCELLED"),
    ("READY_FOR_DISPATCH", "CANCELLED"),
    ("RESERVED", "EXPIRED"),
    ("READY_FOR_DISPATCH", "EXPIRED"),
    ("RECEIVED_PENDING_VERIFICATION", "REJECTED"),
    ("RESERVED", "FAILED"),
    ("READY_FOR_DISPATCH", "FAILED"),
}

APPROVER_ROLES = {
    "PHARMACIST", "APPROVER", "MEDICAL_SUPERINTENDENT",
    "CLINICAL_DIRECTOR", "NETWORK_ADMIN", "FACILITY_ADMIN",
}

CANCELLABLE_WITH_STOCK_RELEASE = {"RESERVED", "READY_FOR_DISPATCH"}
EXPIRABLE_WITH_STOCK_RELEASE = {"RESERVED", "READY_FOR_DISPATCH"}
TERMINAL_STATES = {"CANCELLED", "EXPIRED", "CLOSED", "RECEIVED", "REJECTED", "FAILED"}


class TransferStateMachineError(ValueError):
    pass


class ApprovalError(ValueError):
    pass


class ReservationConflictError(ValueError):
    def __init__(self, message: str, conflict_details: Dict[str, Any]):
        super().__init__(message)
        self.conflict_details = conflict_details


def _assert_transition(current: str, target: str) -> None:
    if (current, target) not in ALLOWED_TRANSFER_TRANSITIONS:
        allowed = [t for f, t in ALLOWED_TRANSFER_TRANSITIONS if f == current]
        raise TransferStateMachineError(
            f"Invalid transfer state transition: {current} -> {target}. "
            f"Allowed from '{current}': {allowed}"
        )


def _audit(db, facility_id, action, entity_type, entity_id,
           before_state=None, after_state=None, actor_id=None,
           reason=None, correlation_id=None):
    ev = AuditEvent(
        facility_id=facility_id,
        actor_id=actor_id or "system",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_state=before_state,
        after_state=after_state,
        reason=reason,
        correlation_id=correlation_id,
    )
    db.add(ev)
    return ev


# ---------------------------------------------------------------------------
# ApprovalService
# ---------------------------------------------------------------------------

class ApprovalService:

    @staticmethod
    def _validate_approver(db, user_id, facility_id, proposal):
        user = db.query(User).filter(User.id == user_id, User.status == "ACTIVE").first()
        if not user:
            raise ApprovalError(f"User {user_id} not found or inactive.")

        if facility_id not in (proposal.source_facility_id, proposal.destination_facility_id):
            raise ApprovalError(
                f"Facility {facility_id} is not a party to proposal {proposal.id}. "
                "Users cannot approve on behalf of unrelated facilities."
            )

        facility = db.query(Facility).filter(Facility.id == facility_id).first()
        if not facility:
            raise ApprovalError(f"Facility {facility_id} not found.")

        has_membership = db.query(FacilityMembership).filter(
            FacilityMembership.user_id == user_id,
            FacilityMembership.facility_id == facility_id,
            FacilityMembership.status == "ACTIVE",
        ).first()

        # Accept if same org or has explicit membership
        if not has_membership and user.organisation_id != facility.organisation_id:
            raise ApprovalError(
                f"User {user.name} has no membership at '{facility.name}' "
                "and is not in the same organisation."
            )

        # Check role — user global role or membership role
        effective_role = user.role
        if has_membership:
            effective_role = has_membership.role

        if effective_role not in APPROVER_ROLES and user.role not in APPROVER_ROLES:
            raise ApprovalError(
                f"User {user.name} (role={user.role}) is not authorised to approve. "
                f"Required: {APPROVER_ROLES}"
            )

        return user

    @staticmethod
    def record_approval(db, proposal_id, facility_id, approver_user_id,
                        proposal_version, decision="APPROVED", reason=None,
                        idempotency_key=None):
        if decision not in ("APPROVED", "REJECTED"):
            raise ApprovalError(f"Invalid decision '{decision}'.")

        proposal = db.query(TransferProposal).filter(
            TransferProposal.id == proposal_id
        ).with_for_update().first()

        if not proposal:
            raise ApprovalError(f"Proposal {proposal_id} not found.")

        if proposal.proposal_version != proposal_version:
            raise ApprovalError(
                f"Stale version: proposal is at v{proposal.proposal_version}, "
                f"approval submitted for v{proposal_version}. Refresh and resubmit."
            )

        if proposal.status in ("RESERVED", "REJECTED", "CANCELLED", "EXPIRED",
                               "FAILED", "FAILED_INSUFFICIENT_STOCK"):
            raise ApprovalError(
                f"Proposal is in terminal state '{proposal.status}' — no new approvals accepted."
            )

        user = ApprovalService._validate_approver(db, approver_user_id, facility_id, proposal)

        # Idempotency check
        existing = db.query(TransferApproval).filter(
            TransferApproval.proposal_id == proposal_id,
            TransferApproval.facility_id == facility_id,
            TransferApproval.proposal_version == proposal_version,
        ).first()
        if existing:
            return {
                "idempotent": True, "status": proposal.status,
                "decision": existing.decision,
                "message": f"Approval for facility {facility_id} v{proposal_version} already recorded.",
            }

        # Record the decision
        appr = TransferApproval(
            proposal_id=proposal_id,
            proposal_version=proposal_version,
            facility_id=facility_id,
            approver_user_id=approver_user_id,
            decision=decision,
            reason=reason or ("Approved" if decision == "APPROVED" else "Rejected"),
        )
        db.add(appr)
        db.flush()

        if decision == "REJECTED":
            before_s = proposal.status
            proposal.status = "REJECTED"
            _audit(db, facility_id, "PROPOSAL_REJECTED", "TRANSFER_PROPOSAL", proposal_id,
                   {"status": before_s}, {"status": "REJECTED"},
                   approver_user_id, reason or "Rejected by facility", proposal_id)
            db.commit()
            return {
                "status": "REJECTED", "decision": "REJECTED",
                "message": f"Proposal rejected by {user.name} ({user.role}).",
                "source_approved": False, "destination_approved": False, "reserved": False,
            }

        # Count current approvals for this version
        all_approved = db.query(TransferApproval).filter(
            TransferApproval.proposal_id == proposal_id,
            TransferApproval.proposal_version == proposal_version,
            TransferApproval.decision == "APPROVED",
        ).all()
        approved_fids = {a.facility_id for a in all_approved}
        has_src = proposal.source_facility_id in approved_fids
        has_dst = proposal.destination_facility_id in approved_fids

        _audit(db, facility_id, "PROPOSAL_APPROVED", "TRANSFER_PROPOSAL", proposal_id,
               {"status": proposal.status},
               {"facility_approved": facility_id, "has_source": has_src, "has_dest": has_dst},
               approver_user_id, reason or "Approved", proposal_id)

        if has_src and not has_dst:
            proposal.status = "PENDING_DESTINATION_APPROVAL"
            db.commit()
            return {
                "status": proposal.status, "decision": "APPROVED",
                "message": f"Source approved by {user.name}. Awaiting destination.",
                "source_approved": True, "destination_approved": False, "reserved": False,
            }

        if has_dst and not has_src:
            proposal.status = "PENDING_SOURCE_APPROVAL"
            db.commit()
            return {
                "status": proposal.status, "decision": "APPROVED",
                "message": f"Destination accepted by {user.name}. Awaiting source.",
                "source_approved": False, "destination_approved": True, "reserved": False,
            }

        if has_src and has_dst:
            proposal.status = "APPROVED"
            db.flush()
            return TransferReservationService.reserve_stock_and_issue_labels(db, proposal)

        db.commit()
        return {
            "status": proposal.status, "decision": "APPROVED",
            "source_approved": has_src, "destination_approved": has_dst, "reserved": False,
        }


# ---------------------------------------------------------------------------
# TransferReservationService
# ---------------------------------------------------------------------------

class TransferReservationService:

    @staticmethod
    def reserve_stock_and_issue_labels(db, proposal, idempotency_key=None):
        # Idempotency guard
        existing = db.query(Transfer).filter(Transfer.proposal_id == proposal.id).first()
        if existing:
            return {
                "status": "RESERVED", "success": True, "idempotent": True,
                "transfer_id": existing.id, "proposal_id": proposal.id,
                "message": "Already reserved (idempotent).",
                "source_approved": True, "destination_approved": True, "reserved": True,
            }

        proposal_batches = db.query(TransferProposalBatch).filter(
            TransferProposalBatch.proposal_id == proposal.id
        ).all()
        if not proposal_batches:
            raise TransferStateMachineError(f"Proposal {proposal.id} has no batch lines.")

        # Phase 1: revalidate under row lock
        conflicts = []
        locked = []
        for pb in proposal_batches:
            inv = db.query(FacilityBatchInventory).filter(
                FacilityBatchInventory.facility_id == proposal.source_facility_id,
                FacilityBatchInventory.batch_id == pb.batch_id,
            ).with_for_update().first()

            batch = db.query(Batch).filter(Batch.id == pb.batch_id).first()

            if not batch:
                conflicts.append({"batch_id": pb.batch_id, "reason": "BATCH_NOT_FOUND",
                                   "required": pb.quantity, "available": 0})
                continue
            if batch.quality_status not in ("RELEASED", "APPROVED"):
                conflicts.append({"batch_id": pb.batch_id, "lot": batch.manufacturer_lot_number,
                                   "reason": f"INELIGIBLE_STATUS:{batch.quality_status}",
                                   "required": pb.quantity, "available": 0})
                continue
            usable = inv.usable_quantity if inv else 0
            if usable < pb.quantity:
                conflicts.append({"batch_id": pb.batch_id, "lot": batch.manufacturer_lot_number,
                                   "reason": "INSUFFICIENT_USABLE_STOCK",
                                   "required": pb.quantity, "available": usable,
                                   "deficit": pb.quantity - usable})
            else:
                locked.append((pb, inv, batch))

        if conflicts:
            proposal.status = "FAILED_INSUFFICIENT_STOCK"
            _audit(db, proposal.source_facility_id, "RESERVATION_FAILED_STOCK_CONFLICT",
                   "TRANSFER_PROPOSAL", proposal.id,
                   {"status": "APPROVED"}, {"status": "FAILED_INSUFFICIENT_STOCK", "conflicts": conflicts},
                   reason="Stock changed after proposal — safe re-planning required",
                   correlation_id=proposal.id)
            db.commit()
            raise ReservationConflictError(
                f"Reservation failed for {len(conflicts)} batch(es). Safe re-planning required.",
                {"conflicts": conflicts, "proposal_id": proposal.id}
            )

        # Phase 2: reserve
        for pb, inv, batch in locked:
            LedgerService.record_movement(
                db=db,
                facility_id=proposal.source_facility_id,
                batch_id=pb.batch_id,
                movement_type="TRANSFER_RESERVATION",
                quantity_delta=pb.quantity,
                unit=pb.unit,
                reference_type="TRANSFER_PROPOSAL",
                reference_id=proposal.id,
                reason=f"Reservation for approved proposal {proposal.id}",
            )

        transfer = Transfer(
            proposal_id=proposal.id,
            status="READY_FOR_DISPATCH",
            source_facility_id=proposal.source_facility_id,
            destination_facility_id=proposal.destination_facility_id,
            tracking_reference=f"TRK-MF-{proposal.id[:8].upper()}",
        )
        db.add(transfer)
        db.flush()

        issued_labels = []
        for i, (pb, inv, batch) in enumerate(locked, 1):
            pkg = TransferPackage(
                transfer_id=transfer.id,
                package_reference=f"PKG-{i:03d}",
                batch_id=pb.batch_id,
                quantity=pb.quantity,
                unit=pb.unit,
                status="PREPARED",
            )
            db.add(pkg)
            db.flush()
            token = generate_secure_opaque_token(prefix=f"MF_{transfer.id[:6].upper()}")
            thash = hash_token(token)
            label = SerializedLabel(
                transfer_package_id=pkg.id,
                token_hash=thash,
                label_version=1,
                status="ISSUED",
            )
            db.add(label)
            issued_labels.append({
                "package_id": pkg.id,
                "package_reference": pkg.package_reference,
                "batch_lot": batch.manufacturer_lot_number,
                "expiry_date": str(batch.expiry_date),
                "quantity": pb.quantity,
                "unit": pb.unit,
                "token": token,
            })

        proposal.status = "RESERVED"
        _audit(db, proposal.source_facility_id, "RESERVE_TRANSFER_STOCK", "TRANSFER", transfer.id,
               {"proposal_status": "APPROVED"},
               {"proposal_status": "RESERVED", "transfer_status": "READY_FOR_DISPATCH",
                "packages": len(issued_labels)},
               reason="Dual approval confirmed; atomic reservation complete",
               correlation_id=proposal.id)
        db.commit()

        return {
            "status": "RESERVED", "success": True,
            "transfer_id": transfer.id, "proposal_id": proposal.id,
            "tracking_reference": transfer.tracking_reference,
            "message": (f"Dual approval confirmed. {proposal.proposed_quantity} units reserved. "
                        f"Transfer {transfer.id[:8]} ready for dispatch."),
            "labels": issued_labels,
            "source_approved": True, "destination_approved": True, "reserved": True,
        }


# ---------------------------------------------------------------------------
# TransferLifecycleService
# ---------------------------------------------------------------------------

class TransferLifecycleService:

    @staticmethod
    def cancel_transfer(db, transfer_id, actor_user_id, reason):
        transfer = db.query(Transfer).filter(
            Transfer.id == transfer_id
        ).with_for_update().first()
        if not transfer:
            raise TransferStateMachineError(f"Transfer {transfer_id} not found.")

        if transfer.status in TERMINAL_STATES:
            return {"status": transfer.status, "idempotent": True,
                    "message": f"Already in terminal state '{transfer.status}'."}

        _assert_transition(transfer.status, "CANCELLED")
        before_s = transfer.status

        if before_s in CANCELLABLE_WITH_STOCK_RELEASE:
            for pkg in db.query(TransferPackage).filter(
                TransferPackage.transfer_id == transfer_id
            ).all():
                ikey = f"cancel_release_{transfer_id}_{pkg.id}"
                try:
                    LedgerService.record_movement(
                        db=db,
                        facility_id=transfer.source_facility_id,
                        batch_id=pkg.batch_id,
                        movement_type="TRANSFER_RESERVATION_RELEASE",
                        quantity_delta=pkg.quantity,
                        unit=pkg.unit,
                        reference_type="TRANSFER",
                        reference_id=transfer_id,
                        actor_id=actor_user_id,
                        idempotency_key=ikey,
                        reason=f"Cancellation release: {reason}",
                    )
                except ValueError as e:
                    logger.warning(f"Release skipped (idempotent): {e}")

        transfer.status = "CANCELLED"
        transfer.closed_at = datetime.now(timezone.utc)
        prop = db.query(TransferProposal).filter(
            TransferProposal.id == transfer.proposal_id
        ).first()
        if prop and prop.status not in ("REJECTED", "CANCELLED"):
            prop.status = "CANCELLED"

        _audit(db, transfer.source_facility_id, "TRANSFER_CANCELLED", "TRANSFER", transfer_id,
               {"status": before_s}, {"status": "CANCELLED"}, actor_user_id, reason,
               transfer.proposal_id)
        db.commit()
        return {
            "status": "CANCELLED", "transfer_id": transfer_id,
            "stock_released": before_s in CANCELLABLE_WITH_STOCK_RELEASE,
            "message": "Transfer cancelled. Reserved stock released.",
        }

    @staticmethod
    def expire_transfer(db, transfer_id, reason="Transfer expired due to timeout"):
        transfer = db.query(Transfer).filter(
            Transfer.id == transfer_id
        ).with_for_update().first()
        if not transfer:
            raise TransferStateMachineError(f"Transfer {transfer_id} not found.")

        if transfer.status in TERMINAL_STATES:
            return {"status": transfer.status, "idempotent": True,
                    "message": "Already in terminal state; expiry no-op."}

        _assert_transition(transfer.status, "EXPIRED")
        before_s = transfer.status

        if before_s in EXPIRABLE_WITH_STOCK_RELEASE:
            for pkg in db.query(TransferPackage).filter(
                TransferPackage.transfer_id == transfer_id
            ).all():
                ikey = f"expire_release_{transfer_id}_{pkg.id}"
                try:
                    LedgerService.record_movement(
                        db=db,
                        facility_id=transfer.source_facility_id,
                        batch_id=pkg.batch_id,
                        movement_type="TRANSFER_RESERVATION_RELEASE",
                        quantity_delta=pkg.quantity,
                        unit=pkg.unit,
                        reference_type="TRANSFER",
                        reference_id=transfer_id,
                        idempotency_key=ikey,
                        reason=f"Expiry release: {reason}",
                    )
                except ValueError as e:
                    logger.warning(f"Expiry release skipped (idempotent): {e}")

        transfer.status = "EXPIRED"
        transfer.closed_at = datetime.now(timezone.utc)
        prop = db.query(TransferProposal).filter(
            TransferProposal.id == transfer.proposal_id
        ).first()
        if prop and prop.status not in ("REJECTED", "CANCELLED", "EXPIRED"):
            prop.status = "EXPIRED"

        _audit(db, transfer.source_facility_id, "TRANSFER_EXPIRED", "TRANSFER", transfer_id,
               {"status": before_s}, {"status": "EXPIRED"}, None, reason, transfer.proposal_id)
        db.commit()
        return {
            "status": "EXPIRED", "transfer_id": transfer_id,
            "stock_released": before_s in EXPIRABLE_WITH_STOCK_RELEASE,
            "message": "Transfer expired. Reserved stock released.", "idempotent": False,
        }

    @staticmethod
    def advance_state(db, transfer_id, target_status, actor_user_id,
                      reason=None, metadata=None):
        transfer = db.query(Transfer).filter(
            Transfer.id == transfer_id
        ).with_for_update().first()
        if not transfer:
            raise TransferStateMachineError(f"Transfer {transfer_id} not found.")

        _assert_transition(transfer.status, target_status)
        before_s = transfer.status
        now = datetime.now(timezone.utc)
        transfer.status = target_status
        if target_status == "DISPATCHED":
            transfer.dispatched_at = now
        elif target_status in ("RECEIVED", "PARTIALLY_RECEIVED", "RECEIVED_PENDING_VERIFICATION"):
            transfer.received_at = now
        elif target_status in ("CLOSED", "CANCELLED", "EXPIRED"):
            transfer.closed_at = now

        _audit(db, transfer.source_facility_id, f"TRANSFER_STATE_{target_status}", "TRANSFER",
               transfer_id, {"status": before_s}, {"status": target_status, **(metadata or {})},
               actor_user_id, reason or f"Advanced to {target_status}", transfer.proposal_id)
        db.commit()
        return {
            "status": target_status, "transfer_id": transfer_id,
            "previous_status": before_s,
            "message": f"Transfer advanced: {before_s} -> {target_status}.",
        }

    @staticmethod
    def trigger_replan(db, failed_proposal_id, actor_user_id,
                       reason="Stock conflict — re-planning triggered"):
        proposal = db.query(TransferProposal).filter(
            TransferProposal.id == failed_proposal_id
        ).first()
        if not proposal:
            raise TransferStateMachineError(f"Proposal {failed_proposal_id} not found.")

        before_v = proposal.proposal_version
        before_s = proposal.status
        proposal.proposal_version += 1
        proposal.status = "PROPOSED"

        _audit(db, proposal.source_facility_id, "PROPOSAL_REPLAN_TRIGGERED",
               "TRANSFER_PROPOSAL", failed_proposal_id,
               {"status": before_s, "version": before_v},
               {"status": "PROPOSED", "version": proposal.proposal_version},
               actor_user_id, reason, failed_proposal_id)
        db.commit()

        return {
            "replan": True, "proposal_id": failed_proposal_id,
            "new_version": proposal.proposal_version,
            "message": (
                f"Proposal bumped v{before_v} -> v{proposal.proposal_version}. "
                "Prior approvals invalidated. Re-approve or regenerate matching."
            ),
            "action_required": "RE_APPROVE_OR_REGENERATE_PROPOSAL",
        }

    @staticmethod
    def get_transfer_detail(db, transfer_id):
        transfer = db.query(Transfer).filter(Transfer.id == transfer_id).first()
        if not transfer:
            return None

        proposal = db.query(TransferProposal).filter(
            TransferProposal.id == transfer.proposal_id
        ).first()

        from app.models.product import Product
        from app.models.organization import Facility as Fac
        product = db.query(Product).filter(
            Product.id == proposal.product_id
        ).first() if proposal else None
        src = db.query(Fac).filter(Fac.id == transfer.source_facility_id).first()
        dest = db.query(Fac).filter(Fac.id == transfer.destination_facility_id).first()

        packages_out = []
        total_qty = 0
        for pkg in transfer.packages:
            label_info = None
            if pkg.label:
                label_info = {
                    "id": pkg.label.id,
                    "label_version": pkg.label.label_version,
                    "status": pkg.label.status,
                    "token_preview": f"HASH_{pkg.label.token_hash[:8]}...",
                    "issued_at": pkg.label.issued_at.isoformat() if pkg.label.issued_at else None,
                }
            packages_out.append({
                "id": pkg.id,
                "package_reference": pkg.package_reference,
                "batch_id": pkg.batch_id,
                "lot_number": pkg.batch.manufacturer_lot_number if pkg.batch else None,
                "expiry_date": str(pkg.batch.expiry_date) if pkg.batch else None,
                "quantity": pkg.quantity, "unit": pkg.unit,
                "status": pkg.status, "label": label_info,
            })
            total_qty += pkg.quantity

        approvals_out = []
        if proposal:
            for a in proposal.approvals:
                approvals_out.append({
                    "id": a.id, "facility_id": a.facility_id,
                    "approver_user_id": a.approver_user_id,
                    "decision": a.decision, "reason": a.reason,
                    "proposal_version": a.proposal_version,
                    "decided_at": a.decided_at.isoformat() if a.decided_at else None,
                })

        scans_out = [{
            "id": s.id, "scan_type": s.scan_type, "result": s.result,
            "facility_id": s.facility_id, "user_id": s.user_id,
            "scanned_at": s.scanned_at.isoformat() if s.scanned_at else None,
        } for s in transfer.scan_events]

        audit_trail = db.query(AuditEvent).filter(
            AuditEvent.entity_id == transfer_id
        ).order_by(AuditEvent.created_at).all()
        audit_out = [{
            "action": e.action, "actor_id": e.actor_id,
            "before_state": e.before_state, "after_state": e.after_state,
            "reason": e.reason,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        } for e in audit_trail]

        return {
            "id": transfer.id,
            "proposal_id": transfer.proposal_id,
            "tracking_reference": transfer.tracking_reference,
            "status": transfer.status,
            "source_facility_id": transfer.source_facility_id,
            "source_facility_name": src.name if src else "Unknown",
            "destination_facility_id": transfer.destination_facility_id,
            "destination_facility_name": dest.name if dest else "Unknown",
            "product_id": proposal.product_id if proposal else None,
            "product_name": product.name if product else "Unknown",
            "proposal_version": proposal.proposal_version if proposal else None,
            "proposed_quantity": proposal.proposed_quantity if proposal else total_qty,
            "unit": proposal.unit if proposal else "UNIT",
            "priority": proposal.priority if proposal else "MEDIUM",
            "source_rationale": proposal.source_rationale if proposal else {},
            "destination_rationale": proposal.destination_rationale if proposal else {},
            "created_at": transfer.created_at.isoformat() if transfer.created_at else None,
            "dispatched_at": transfer.dispatched_at.isoformat() if transfer.dispatched_at else None,
            "received_at": transfer.received_at.isoformat() if transfer.received_at else None,
            "closed_at": transfer.closed_at.isoformat() if transfer.closed_at else None,
            "packages": packages_out,
            "approvals": approvals_out,
            "scan_events": scans_out,
            "audit_trail": audit_out,
        }

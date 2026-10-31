"""
test_transfer_state_machine.py
Comprehensive tests for:
- Dual-facility approval with role/membership/version enforcement
- Missing approvals, wrong facility, wrong role, stale version
- Concurrency-safe reservation with row locking
- Stock conflict detection and structured conflict response
- Duplicate reservation idempotency
- Cancellation with exactly-once stock release
- Expiry with exactly-once stock release
- Concurrent reservations (only one succeeds)
- Re-planning path after rejection/failure
- State machine transition validation
"""
import threading
import pytest
from datetime import date, timedelta, datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.organization import Organisation, Facility, User, FacilityMembership
from app.models.product import Product, Batch
from app.models.inventory import FacilityBatchInventory
from app.models.proposal import TransferProposal, TransferProposalBatch, TransferApproval
from app.models.transfer import Transfer, TransferPackage
from app.models.audit import AuditEvent

from app.services.transfer_service import (
    ApprovalService, TransferReservationService, TransferLifecycleService,
    ApprovalError, ReservationConflictError, TransferStateMachineError,
    ALLOWED_TRANSFER_TRANSITIONS,
)
from app.services.ledger_service import LedgerService


import uuid
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# Test database setup (SQLite in-memory per test)
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from sqlalchemy import event as sa_event

    @sa_event.listens_for(eng, "connect")
    def set_sqlite_pragma(conn, _):
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(eng)
    eng.dispose()


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _seed_org(db):
    org = Organisation(name="Test Healthcare Network", status="ACTIVE")
    db.add(org)
    db.flush()
    return org


def _seed_facilities(db, org_id):
    src = Facility(
        organisation_id=org_id, name="Source Hospital", facility_type="HOSPITAL",
        timezone="UTC", status="ACTIVE",
        storage_capabilities={"cold_chain": True, "ambient_max_c": 25, "narcotics_vault": True}
    )
    dst = Facility(
        organisation_id=org_id, name="Destination Pharmacy", facility_type="PHARMACY",
        timezone="UTC", status="ACTIVE",
        storage_capabilities={"cold_chain": True, "ambient_max_c": 22, "narcotics_vault": False}
    )
    db.add_all([src, dst])
    db.flush()
    return src, dst


def _seed_users(db, org_id, src_id, dst_id):
    approver_src = User(
        organisation_id=org_id, email=f"src_approver_{org_id[:6]}@test.com",
        name="Source Approver", role="PHARMACIST", status="ACTIVE"
    )
    approver_dst = User(
        organisation_id=org_id, email=f"dst_approver_{org_id[:6]}@test.com",
        name="Dest Approver", role="MEDICAL_SUPERINTENDENT", status="ACTIVE"
    )
    no_role_user = User(
        organisation_id=org_id, email=f"viewer_{org_id[:6]}@test.com",
        name="Viewer Only", role="VIEWER", status="ACTIVE"
    )
    # Create a real separate org so FK is satisfied
    other_org = Organisation(name="Other Healthcare Org", status="ACTIVE")
    db.add(other_org)
    db.flush()
    wrong_org_user = User(
        organisation_id=other_org.id, email=f"stranger_{org_id[:6]}@other.com",
        name="Stranger", role="PHARMACIST", status="ACTIVE"
    )
    db.add_all([approver_src, approver_dst, no_role_user, wrong_org_user])
    db.flush()
    return approver_src, approver_dst, no_role_user, wrong_org_user


def _seed_product_and_batch(db, expiry_days=180):
    uid = uuid.uuid4().hex[:8]
    product = Product(
        internal_code=f"TEST-MED-{uid}", name="Test Medicine 500mg",
        generic_name="Testmedicin", strength="500mg", dosage_form="TABLET",
        pack_size=100, base_unit="UNIT", storage_requirements="ROOM_TEMPERATURE",
        transfer_policy_code="STANDARD_ELIGIBLE", status="ACTIVE"
    )
    db.add(product)
    db.flush()

    batch = Batch(
        product_id=product.id,
        manufacturer_lot_number=f"LOT-TEST-{uid}",
        expiry_date=date.today() + timedelta(days=expiry_days),
        manufacturer="TestPharma",
        quality_status="RELEASED",
    )
    db.add(batch)
    db.flush()
    return product, batch


def _seed_inventory(db, facility_id, batch_id, on_hand=500, reserved=0):
    inv = FacilityBatchInventory(
        facility_id=facility_id, batch_id=batch_id,
        on_hand_quantity=on_hand, reserved_quantity=reserved,
        quarantined_quantity=0, damaged_quantity=0,
        unit="UNIT", version=1,
    )
    db.add(inv)
    db.flush()
    return inv


def _seed_proposal(db, src_id, dst_id, product_id, batch_id, quantity=100):
    proposal = TransferProposal(
        source_facility_id=src_id, destination_facility_id=dst_id,
        product_id=product_id, proposed_quantity=quantity, unit="UNIT",
        status="PROPOSED", priority="HIGH",
        source_rationale={"surplus": quantity, "buffer_days": 40},
        destination_rationale={"deficit_days": 5, "projected_stockout": "2026-11-10"},
        proposal_version=1,
    )
    db.add(proposal)
    db.flush()
    pb = TransferProposalBatch(
        proposal_id=proposal.id, batch_id=batch_id,
        quantity=quantity, unit="UNIT"
    )
    db.add(pb)
    db.flush()
    db.commit()
    return proposal


# ---------------------------------------------------------------------------
# Test: State machine — disallowed transitions
# ---------------------------------------------------------------------------

class TestStateMachineTransitions:

    def test_allowed_transitions_are_accepted(self):
        """All transitions in the allowed set must not raise."""
        from app.services.transfer_service import _assert_transition
        for (f, t) in ALLOWED_TRANSFER_TRANSITIONS:
            _assert_transition(f, t)  # must not raise

    def test_disallowed_transition_raises(self):
        from app.services.transfer_service import _assert_transition
        with pytest.raises(TransferStateMachineError):
            _assert_transition("RESERVED", "RECEIVED")  # cannot skip dispatch

    def test_cannot_transition_from_closed(self):
        from app.services.transfer_service import _assert_transition
        with pytest.raises(TransferStateMachineError):
            _assert_transition("CLOSED", "DISPATCHED")

    def test_cannot_transition_from_received_to_dispatched(self):
        from app.services.transfer_service import _assert_transition
        with pytest.raises(TransferStateMachineError):
            _assert_transition("RECEIVED", "DISPATCHED")


# ---------------------------------------------------------------------------
# Test: Wrong facility / wrong role / stale version
# ---------------------------------------------------------------------------

class TestApprovalGovernance:

    def test_missing_approval_second_party(self, db):
        """Only one facility approved — proposal should be PENDING_DESTINATION_APPROVAL."""
        org = _seed_org(db)
        src, dst = _seed_facilities(db, org.id)
        approver_src, approver_dst, _, _ = _seed_users(db, org.id, src.id, dst.id)
        product, batch = _seed_product_and_batch(db)
        _seed_inventory(db, src.id, batch.id, on_hand=500)
        proposal = _seed_proposal(db, src.id, dst.id, product.id, batch.id, quantity=100)

        result = ApprovalService.record_approval(
            db=db,
            proposal_id=proposal.id,
            facility_id=src.id,
            approver_user_id=approver_src.id,
            proposal_version=1,
            decision="APPROVED",
        )
        assert result["source_approved"] is True
        assert result["destination_approved"] is False
        assert result["status"] == "PENDING_DESTINATION_APPROVAL"
        assert not result.get("reserved", False)

    def test_wrong_facility_rejected(self, db):
        """User claiming to approve for a facility they are not party to is rejected."""
        org = _seed_org(db)
        src, dst = _seed_facilities(db, org.id)
        approver_src, approver_dst, _, _ = _seed_users(db, org.id, src.id, dst.id)
        product, batch = _seed_product_and_batch(db)
        _seed_inventory(db, src.id, batch.id, on_hand=500)
        proposal = _seed_proposal(db, src.id, dst.id, product.id, batch.id)

        # Create a third unrelated facility
        other_fac = Facility(
            organisation_id=org.id, name="Other Clinic", facility_type="HOSPITAL",
            timezone="UTC", status="ACTIVE"
        )
        db.add(other_fac)
        db.flush()

        with pytest.raises(ApprovalError, match="not a party"):
            ApprovalService.record_approval(
                db=db,
                proposal_id=proposal.id,
                facility_id=other_fac.id,
                approver_user_id=approver_src.id,
                proposal_version=1,
                decision="APPROVED",
            )

    def test_wrong_role_rejected(self, db):
        """A user with VIEWER role cannot approve a transfer."""
        org = _seed_org(db)
        src, dst = _seed_facilities(db, org.id)
        approver_src, approver_dst, viewer, _ = _seed_users(db, org.id, src.id, dst.id)
        product, batch = _seed_product_and_batch(db)
        _seed_inventory(db, src.id, batch.id, on_hand=500)
        proposal = _seed_proposal(db, src.id, dst.id, product.id, batch.id)

        with pytest.raises(ApprovalError, match="not authorised"):
            ApprovalService.record_approval(
                db=db,
                proposal_id=proposal.id,
                facility_id=src.id,
                approver_user_id=viewer.id,
                proposal_version=1,
                decision="APPROVED",
            )

    def test_stale_proposal_version_rejected(self, db):
        """Approval for wrong proposal_version must be rejected."""
        org = _seed_org(db)
        src, dst = _seed_facilities(db, org.id)
        approver_src, approver_dst, _, _ = _seed_users(db, org.id, src.id, dst.id)
        product, batch = _seed_product_and_batch(db)
        _seed_inventory(db, src.id, batch.id, on_hand=500)
        proposal = _seed_proposal(db, src.id, dst.id, product.id, batch.id)

        with pytest.raises(ApprovalError, match="Stale version"):
            ApprovalService.record_approval(
                db=db,
                proposal_id=proposal.id,
                facility_id=src.id,
                approver_user_id=approver_src.id,
                proposal_version=99,  # wrong version
                decision="APPROVED",
            )

    def test_cannot_approve_terminal_proposal(self, db):
        """A REJECTED proposal cannot receive new approvals."""
        org = _seed_org(db)
        src, dst = _seed_facilities(db, org.id)
        approver_src, approver_dst, _, _ = _seed_users(db, org.id, src.id, dst.id)
        product, batch = _seed_product_and_batch(db)
        _seed_inventory(db, src.id, batch.id, on_hand=500)
        proposal = _seed_proposal(db, src.id, dst.id, product.id, batch.id)
        proposal.status = "REJECTED"
        db.commit()

        with pytest.raises(ApprovalError, match="terminal state"):
            ApprovalService.record_approval(
                db=db,
                proposal_id=proposal.id,
                facility_id=src.id,
                approver_user_id=approver_src.id,
                proposal_version=1,
                decision="APPROVED",
            )

    def test_rejection_preserves_history(self, db):
        """Rejection must create a TransferApproval record and NOT delete the proposal."""
        org = _seed_org(db)
        src, dst = _seed_facilities(db, org.id)
        approver_src, approver_dst, _, _ = _seed_users(db, org.id, src.id, dst.id)
        product, batch = _seed_product_and_batch(db)
        _seed_inventory(db, src.id, batch.id, on_hand=500)
        proposal = _seed_proposal(db, src.id, dst.id, product.id, batch.id)

        result = ApprovalService.record_approval(
            db=db,
            proposal_id=proposal.id,
            facility_id=src.id,
            approver_user_id=approver_src.id,
            proposal_version=1,
            decision="REJECTED",
            reason="Stock condition not acceptable",
        )
        assert result["status"] == "REJECTED"
        db.refresh(proposal)
        assert proposal.status == "REJECTED"

        # History preserved
        appr = db.query(TransferApproval).filter(
            TransferApproval.proposal_id == proposal.id
        ).first()
        assert appr is not None
        assert appr.decision == "REJECTED"
        assert appr.reason == "Stock condition not acceptable"

    def test_dual_approval_triggers_reservation(self, db):
        """Both parties approving must trigger automatic stock reservation."""
        org = _seed_org(db)
        src, dst = _seed_facilities(db, org.id)
        approver_src, approver_dst, _, _ = _seed_users(db, org.id, src.id, dst.id)
        product, batch = _seed_product_and_batch(db)
        _seed_inventory(db, src.id, batch.id, on_hand=500)
        proposal = _seed_proposal(db, src.id, dst.id, product.id, batch.id, quantity=100)

        # Source approves
        r1 = ApprovalService.record_approval(
            db=db, proposal_id=proposal.id, facility_id=src.id,
            approver_user_id=approver_src.id, proposal_version=1, decision="APPROVED",
        )
        assert r1["source_approved"] is True
        assert r1.get("reserved") is False

        # Destination approves → triggers reservation
        r2 = ApprovalService.record_approval(
            db=db, proposal_id=proposal.id, facility_id=dst.id,
            approver_user_id=approver_dst.id, proposal_version=1, decision="APPROVED",
        )
        assert r2["reserved"] is True
        assert r2["status"] == "RESERVED"
        assert "transfer_id" in r2

        # Verify inventory updated (reserved quantity increased)
        inv = db.query(FacilityBatchInventory).filter(
            FacilityBatchInventory.facility_id == src.id,
            FacilityBatchInventory.batch_id == batch.id,
        ).first()
        assert inv.reserved_quantity == 100
        assert inv.usable_quantity == 400  # 500 - 100 reserved

    def test_duplicate_approval_is_idempotent(self, db):
        """Re-submitting the same approval for same facility+version returns idempotent flag."""
        org = _seed_org(db)
        src, dst = _seed_facilities(db, org.id)
        approver_src, approver_dst, _, _ = _seed_users(db, org.id, src.id, dst.id)
        product, batch = _seed_product_and_batch(db)
        _seed_inventory(db, src.id, batch.id, on_hand=500)
        proposal = _seed_proposal(db, src.id, dst.id, product.id, batch.id)

        ApprovalService.record_approval(
            db=db, proposal_id=proposal.id, facility_id=src.id,
            approver_user_id=approver_src.id, proposal_version=1, decision="APPROVED",
        )
        r2 = ApprovalService.record_approval(
            db=db, proposal_id=proposal.id, facility_id=src.id,
            approver_user_id=approver_src.id, proposal_version=1, decision="APPROVED",
        )
        assert r2.get("idempotent") is True


# ---------------------------------------------------------------------------
# Test: Stock conflict detection
# ---------------------------------------------------------------------------

class TestReservationConflict:

    def test_stock_conflict_returns_conflict_details(self, db):
        """If stock drops between proposal and reservation, structured conflict is returned."""
        org = _seed_org(db)
        src, dst = _seed_facilities(db, org.id)
        approver_src, approver_dst, _, _ = _seed_users(db, org.id, src.id, dst.id)
        product, batch = _seed_product_and_batch(db)
        # Seed only 50 units but propose 100
        _seed_inventory(db, src.id, batch.id, on_hand=50)
        proposal = _seed_proposal(db, src.id, dst.id, product.id, batch.id, quantity=100)

        with pytest.raises(ReservationConflictError) as exc_info:
            TransferReservationService.reserve_stock_and_issue_labels(db, proposal)

        err = exc_info.value
        assert err.conflict_details["conflicts"][0]["reason"] == "INSUFFICIENT_USABLE_STOCK"
        assert err.conflict_details["conflicts"][0]["available"] == 50

        db.refresh(proposal)
        assert proposal.status == "FAILED_INSUFFICIENT_STOCK"

    def test_blocked_batch_detected_in_reservation(self, db):
        """A batch whose quality_status is not RELEASED/APPROVED is rejected during reservation."""
        org = _seed_org(db)
        src, dst = _seed_facilities(db, org.id)
        approver_src, approver_dst, _, _ = _seed_users(db, org.id, src.id, dst.id)
        product, batch = _seed_product_and_batch(db)
        batch.quality_status = "QUARANTINED"
        db.flush()
        _seed_inventory(db, src.id, batch.id, on_hand=500)
        proposal = _seed_proposal(db, src.id, dst.id, product.id, batch.id, quantity=100)

        with pytest.raises(ReservationConflictError) as exc_info:
            TransferReservationService.reserve_stock_and_issue_labels(db, proposal)

        assert "INELIGIBLE_STATUS" in exc_info.value.conflict_details["conflicts"][0]["reason"]

    def test_duplicate_reservation_is_idempotent(self, db):
        """Calling reserve twice returns the same transfer (no double-debit)."""
        org = _seed_org(db)
        src, dst = _seed_facilities(db, org.id)
        approver_src, approver_dst, _, _ = _seed_users(db, org.id, src.id, dst.id)
        product, batch = _seed_product_and_batch(db)
        _seed_inventory(db, src.id, batch.id, on_hand=500)
        proposal = _seed_proposal(db, src.id, dst.id, product.id, batch.id, quantity=100)

        r1 = TransferReservationService.reserve_stock_and_issue_labels(db, proposal)
        r2 = TransferReservationService.reserve_stock_and_issue_labels(db, proposal)

        assert r1["transfer_id"] == r2["transfer_id"]
        assert r2.get("idempotent") is True

        # Inventory must not be double-debited
        inv = db.query(FacilityBatchInventory).filter(
            FacilityBatchInventory.facility_id == src.id,
            FacilityBatchInventory.batch_id == batch.id,
        ).first()
        assert inv.reserved_quantity == 100  # not 200


# ---------------------------------------------------------------------------
# Test: Cancellation and expiry
# ---------------------------------------------------------------------------

class TestCancellationAndExpiry:

    def _create_reserved_transfer(self, db):
        org = _seed_org(db)
        src, dst = _seed_facilities(db, org.id)
        approver_src, approver_dst, _, _ = _seed_users(db, org.id, src.id, dst.id)
        product, batch = _seed_product_and_batch(db)
        _seed_inventory(db, src.id, batch.id, on_hand=500)
        proposal = _seed_proposal(db, src.id, dst.id, product.id, batch.id, quantity=100)
        r = TransferReservationService.reserve_stock_and_issue_labels(db, proposal)
        transfer_id = r["transfer_id"]
        return src, dst, batch, transfer_id, approver_src

    def test_cancellation_releases_stock_once(self, db):
        src, dst, batch, transfer_id, actor = self._create_reserved_transfer(db)

        inv_before = db.query(FacilityBatchInventory).filter(
            FacilityBatchInventory.facility_id == src.id,
            FacilityBatchInventory.batch_id == batch.id,
        ).first()
        assert inv_before.reserved_quantity == 100

        result = TransferLifecycleService.cancel_transfer(
            db, transfer_id, actor.id, "Clinical team withdrew request"
        )
        assert result["status"] == "CANCELLED"
        assert result["stock_released"] is True

        inv_after = db.query(FacilityBatchInventory).filter(
            FacilityBatchInventory.facility_id == src.id,
            FacilityBatchInventory.batch_id == batch.id,
        ).first()
        assert inv_after.reserved_quantity == 0
        assert inv_after.usable_quantity == 500

    def test_cancellation_is_idempotent_second_call(self, db):
        """Cancelling an already-cancelled transfer returns idempotent flag without error."""
        _, _, _, transfer_id, actor = self._create_reserved_transfer(db)
        TransferLifecycleService.cancel_transfer(db, transfer_id, actor.id, "First cancel")
        r2 = TransferLifecycleService.cancel_transfer(db, transfer_id, actor.id, "Second cancel")
        assert r2.get("idempotent") is True

    def test_expiry_releases_stock_once(self, db):
        src, dst, batch, transfer_id, _ = self._create_reserved_transfer(db)

        result = TransferLifecycleService.expire_transfer(
            db, transfer_id, "Expected arrival window elapsed"
        )
        assert result["status"] == "EXPIRED"
        assert result["stock_released"] is True

        inv = db.query(FacilityBatchInventory).filter(
            FacilityBatchInventory.facility_id == src.id,
            FacilityBatchInventory.batch_id == batch.id,
        ).first()
        assert inv.reserved_quantity == 0

    def test_expiry_is_idempotent_second_call(self, db):
        _, _, _, transfer_id, _ = self._create_reserved_transfer(db)
        TransferLifecycleService.expire_transfer(db, transfer_id, "First expiry")
        r2 = TransferLifecycleService.expire_transfer(db, transfer_id, "Second expiry")
        assert r2.get("idempotent") is True

    def test_cannot_cancel_from_dispatched(self, db):
        _, _, _, transfer_id, actor = self._create_reserved_transfer(db)
        # Advance to DISPATCHED first
        t = db.query(Transfer).filter(Transfer.id == transfer_id).first()
        t.status = "DISPATCHED"
        db.commit()

        with pytest.raises(TransferStateMachineError):
            TransferLifecycleService.cancel_transfer(db, transfer_id, actor.id, "Too late")


# ---------------------------------------------------------------------------
# Test: Re-planning
# ---------------------------------------------------------------------------

class TestReplanning:

    def test_replan_bumps_version_and_invalidates_approvals(self, db):
        org = _seed_org(db)
        src, dst = _seed_facilities(db, org.id)
        approver_src, approver_dst, _, _ = _seed_users(db, org.id, src.id, dst.id)
        product, batch = _seed_product_and_batch(db)
        _seed_inventory(db, src.id, batch.id, on_hand=500)
        proposal = _seed_proposal(db, src.id, dst.id, product.id, batch.id)

        # Record source approval at v1
        ApprovalService.record_approval(
            db=db, proposal_id=proposal.id, facility_id=src.id,
            approver_user_id=approver_src.id, proposal_version=1, decision="APPROVED",
        )

        result = TransferLifecycleService.trigger_replan(
            db, proposal.id, approver_src.id, "Source inventory changed"
        )
        assert result["replan"] is True
        assert result["new_version"] == 2

        # Stale approval at v1 must now be rejected
        db.refresh(proposal)
        assert proposal.proposal_version == 2

        with pytest.raises(ApprovalError, match="Stale version"):
            ApprovalService.record_approval(
                db=db, proposal_id=proposal.id, facility_id=src.id,
                approver_user_id=approver_src.id, proposal_version=1,  # old version
                decision="APPROVED",
            )

    def test_replan_after_stock_conflict_allows_fresh_approval(self, db):
        org = _seed_org(db)
        src, dst = _seed_facilities(db, org.id)
        approver_src, approver_dst, _, _ = _seed_users(db, org.id, src.id, dst.id)
        product, batch = _seed_product_and_batch(db)
        _seed_inventory(db, src.id, batch.id, on_hand=500)
        proposal = _seed_proposal(db, src.id, dst.id, product.id, batch.id, quantity=100)

        proposal.status = "FAILED_INSUFFICIENT_STOCK"
        db.commit()

        result = TransferLifecycleService.trigger_replan(
            db, proposal.id, approver_src.id, "Restocked — retrying"
        )
        assert result["new_version"] == 2
        db.refresh(proposal)
        assert proposal.status == "PROPOSED"


# ---------------------------------------------------------------------------
# Test: Concurrent reservations (at most one succeeds)
# ---------------------------------------------------------------------------

class TestConcurrentReservations:
    """
    NOTE: SQLite does not provide true multi-process concurrency or serializable
    row locking equivalent to PostgreSQL/YugabyteDB. This test validates that
    the application-level logic (SELECT FOR UPDATE + idempotency) prevents
    double-reservation within the SAME thread (simulated sequential contention).

    For true concurrent multi-connection locking, run against a
    PostgreSQL/YugabyteDB instance as integration test.
    """

    def test_sequential_double_reservation_blocked(self, db):
        """
        If two reservation calls arrive for the same proposal, the second is idempotent.
        Validates idempotency guard — only one Transfer is created.
        """
        org = _seed_org(db)
        src, dst = _seed_facilities(db, org.id)
        product, batch = _seed_product_and_batch(db)
        _seed_inventory(db, src.id, batch.id, on_hand=200)
        proposal = _seed_proposal(db, src.id, dst.id, product.id, batch.id, quantity=100)

        r1 = TransferReservationService.reserve_stock_and_issue_labels(db, proposal)
        r2 = TransferReservationService.reserve_stock_and_issue_labels(db, proposal)

        assert r1["transfer_id"] == r2["transfer_id"]
        assert r2.get("idempotent") is True

        transfers = db.query(Transfer).filter(Transfer.proposal_id == proposal.id).all()
        assert len(transfers) == 1

        inv = db.query(FacilityBatchInventory).filter(
            FacilityBatchInventory.facility_id == src.id,
            FacilityBatchInventory.batch_id == batch.id,
        ).first()
        assert inv.reserved_quantity == 100  # Not doubled

    def test_insufficient_stock_second_reservation_fails(self, db):
        """
        Two proposals each wanting 150 units from a pool of 200.
        First reservation succeeds; second sees only 50 available and must fail.
        """
        org = _seed_org(db)
        src, dst = _seed_facilities(db, org.id)
        product, batch = _seed_product_and_batch(db)
        _seed_inventory(db, src.id, batch.id, on_hand=200)

        proposal_a = _seed_proposal(db, src.id, dst.id, product.id, batch.id, quantity=150)
        proposal_b = _seed_proposal(db, src.id, dst.id, product.id, batch.id, quantity=150)

        # First reservation succeeds
        r1 = TransferReservationService.reserve_stock_and_issue_labels(db, proposal_a)
        assert r1["success"] is True

        # Second reservation fails due to insufficient remaining stock (200-150=50 < 150)
        with pytest.raises(ReservationConflictError) as exc_info:
            TransferReservationService.reserve_stock_and_issue_labels(db, proposal_b)

        conflict = exc_info.value.conflict_details["conflicts"][0]
        assert conflict["reason"] == "INSUFFICIENT_USABLE_STOCK"
        assert conflict["available"] == 50
        assert conflict["required"] == 150

        # NOTE: For true concurrent lock contention (two DB connections racing):
        # Deploy against PostgreSQL/YugabyteDB and run:
        #   pytest tests/test_transfer_state_machine.py::TestConcurrentReservations
        #           --integration-db postgresql://...
        # The SELECT FOR UPDATE in reserve_stock_and_issue_labels ensures serialized
        # access per inventory row, so at most one concurrent reservation succeeds.


# ---------------------------------------------------------------------------
# Test: Advance state
# ---------------------------------------------------------------------------

class TestStateAdvancement:

    def test_advance_ready_to_dispatched(self, db):
        org = _seed_org(db)
        src, dst = _seed_facilities(db, org.id)
        approver_src, approver_dst, _, _ = _seed_users(db, org.id, src.id, dst.id)
        product, batch = _seed_product_and_batch(db)
        _seed_inventory(db, src.id, batch.id, on_hand=500)
        proposal = _seed_proposal(db, src.id, dst.id, product.id, batch.id)
        r = TransferReservationService.reserve_stock_and_issue_labels(db, proposal)
        transfer_id = r["transfer_id"]

        result = TransferLifecycleService.advance_state(
            db, transfer_id, "DISPATCHED", approver_src.id, "Dispatched by courier"
        )
        assert result["status"] == "DISPATCHED"
        t = db.query(Transfer).filter(Transfer.id == transfer_id).first()
        assert t.dispatched_at is not None

    def test_invalid_advance_raises(self, db):
        org = _seed_org(db)
        src, dst = _seed_facilities(db, org.id)
        product, batch = _seed_product_and_batch(db)
        _seed_inventory(db, src.id, batch.id, on_hand=500)
        proposal = _seed_proposal(db, src.id, dst.id, product.id, batch.id)
        r = TransferReservationService.reserve_stock_and_issue_labels(db, proposal)

        with pytest.raises(TransferStateMachineError):
            TransferLifecycleService.advance_state(
                db, r["transfer_id"], "RECEIVED",  # must go through DISPATCHED first
                "some-user", "Skipping dispatch"
            )

    def test_full_happy_path_lifecycle(self, db):
        """RESERVED -> DISPATCHED -> IN_TRANSIT -> RECEIVED_PENDING_VERIFICATION -> RECEIVED -> CLOSED."""
        org = _seed_org(db)
        src, dst = _seed_facilities(db, org.id)
        approver_src, approver_dst, _, _ = _seed_users(db, org.id, src.id, dst.id)
        product, batch = _seed_product_and_batch(db)
        _seed_inventory(db, src.id, batch.id, on_hand=500)
        proposal = _seed_proposal(db, src.id, dst.id, product.id, batch.id, quantity=100)
        r = TransferReservationService.reserve_stock_and_issue_labels(db, proposal)
        tid = r["transfer_id"]

        for step in ["DISPATCHED", "IN_TRANSIT", "RECEIVED_PENDING_VERIFICATION",
                     "RECEIVED", "CLOSED"]:
            res = TransferLifecycleService.advance_state(
                db, tid, step, approver_src.id, f"Step: {step}"
            )
            assert res["status"] == step

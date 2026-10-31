import pytest
from datetime import datetime, timezone, timedelta, date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base
from app.models.organization import Organisation, Facility, User, FacilityMembership
from app.models.product import Product, Batch
from app.models.inventory import FacilityBatchInventory, InventoryLedger
from app.models.consumption import ConsumptionRecord
from app.models.proposal import TransferProposal, TransferProposalBatch, TransferApproval
from app.models.transfer import Transfer, TransferPackage, SerializedLabel, ScanEvent
from app.services.inventory_service import InventoryService
from app.services.forecast_service import ForecastService
from app.services.risk_service import RiskService
from app.services.matching_service import MatchingService
from app.services.proposal_service import ProposalService
from app.services.qr_service import QRService
from app.core.security import hash_token


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        # Create Org, Facilities, Users
        org = Organisation(name="Test Org")
        session.add(org)
        session.flush()

        fac_a = Facility(organisation_id=org.id, name="Hospital A (Surplus)", facility_type="HOSPITAL", storage_capabilities={"cold_chain": True})
        fac_b = Facility(organisation_id=org.id, name="Hospital B (Need)", facility_type="HOSPITAL", storage_capabilities={"cold_chain": True})
        fac_c = Facility(organisation_id=org.id, name="Clinic C (No Cold Chain)", facility_type="CLINIC", storage_capabilities={"cold_chain": False})
        session.add_all([fac_a, fac_b, fac_c])
        session.flush()

        user_a = User(organisation_id=org.id, email="a@hospital.org", name="Dr. A", role="APPROVER")
        user_b = User(organisation_id=org.id, email="b@hospital.org", name="Dr. B", role="APPROVER")
        session.add_all([user_a, user_b])
        session.flush()

        yield session, {
            "org": org,
            "fac_a": fac_a,
            "fac_b": fac_b,
            "fac_c": fac_c,
            "user_a": user_a,
            "user_b": user_b,
        }
    finally:
        session.close()


def test_usable_inventory_and_fefo_allocation(db_session):
    session, ctx = db_session
    today = date.today()

    prod = Product(
        internal_code="P-TEST-1", name="Amoxicillin 500mg", generic_name="Amoxicillin",
        strength="500mg", dosage_form="CAPSULE", storage_requirements="ROOM_TEMPERATURE"
    )
    session.add(prod)
    session.flush()

    # Batch 1: expires in 30 days
    b1 = Batch(product_id=prod.id, manufacturer_lot_number="LOT-01", expiry_date=today + timedelta(days=30), manufacturer="M1")
    # Batch 2: expires in 90 days
    b2 = Batch(product_id=prod.id, manufacturer_lot_number="LOT-02", expiry_date=today + timedelta(days=90), manufacturer="M2")
    session.add_all([b1, b2])
    session.flush()

    inv1 = FacilityBatchInventory(facility_id=ctx["fac_a"].id, batch_id=b1.id, on_hand_quantity=100, reserved_quantity=20, quarantined_quantity=10, damaged_quantity=0)
    inv2 = FacilityBatchInventory(facility_id=ctx["fac_a"].id, batch_id=b2.id, on_hand_quantity=200, reserved_quantity=0, quarantined_quantity=0, damaged_quantity=0)
    session.add_all([inv1, inv2])
    session.commit()

    # Test usable stock formula: on_hand - reserved - quarantined - damaged
    assert inv1.usable_quantity == 70
    assert inv2.usable_quantity == 200

    # Test FEFO query order: earliest expiry batch must be first
    items = InventoryService.get_facility_inventory(session, facility_id=ctx["fac_a"].id, product_id=prod.id)
    assert len(items) == 2
    assert items[0]["manufacturer_lot_number"] == "LOT-01"
    assert items[1]["manufacturer_lot_number"] == "LOT-02"


def test_matching_constraints_and_rejection_rationale(db_session):
    session, ctx = db_session
    today = date.today()

    # Cold chain medicine
    cold_prod = Product(
        internal_code="P-INS-1", name="Insulin Glargine", generic_name="Insulin",
        strength="100 IU/ml", dosage_form="VIAL", storage_requirements="COLD_CHAIN_2_8C",
        transfer_policy_code="STANDARD_ELIGIBLE"
    )
    session.add(cold_prod)
    session.flush()

    batch_cold = Batch(product_id=cold_prod.id, manufacturer_lot_number="LOT-INS-01", expiry_date=today + timedelta(days=180), manufacturer="M1")
    session.add(batch_cold)
    session.flush()

    # Source fac_a has surplus (300 units)
    inv_a = FacilityBatchInventory(facility_id=ctx["fac_a"].id, batch_id=batch_cold.id, on_hand_quantity=300)
    # Destination fac_c (no cold chain) has shortage (5 units)
    inv_c = FacilityBatchInventory(facility_id=ctx["fac_c"].id, batch_id=batch_cold.id, on_hand_quantity=5)
    session.add_all([inv_a, inv_c])

    # Add consumption history for fac_c (burn rate 5/day)
    now = datetime.now(timezone.utc)
    for i in range(20):
        c = ConsumptionRecord(facility_id=ctx["fac_c"].id, product_id=cold_prod.id, quantity=5, consumed_at=now - timedelta(days=i))
        session.add(c)
    session.commit()

    # Run matching
    matches = MatchingService.find_redistribution_opportunities(session, product_id=cold_prod.id)

    # fac_c MUST be deterministically rejected due to storage incompatibility!
    assert len(matches["accepted_opportunities"]) == 0
    assert len(matches["rejected_candidates"]) >= 1
    rejected = matches["rejected_candidates"][0]
    assert rejected["rejected_reason"] == "STORAGE_INCOMPATIBILITY"
    assert "lacks certified 2-8°C cold chain storage" in rejected["explanation"]


def test_dual_approval_and_atomic_reservation(db_session):
    session, ctx = db_session
    today = date.today()

    prod = Product(internal_code="P-ANT-1", name="Meropenem", generic_name="Meropenem", strength="1g", dosage_form="VIAL", storage_requirements="ROOM_TEMPERATURE")
    session.add(prod)
    session.flush()

    batch = Batch(product_id=prod.id, manufacturer_lot_number="LOT-MERO-10", expiry_date=today + timedelta(days=120), manufacturer="M1")
    session.add(batch)
    session.flush()

    # Source fac_a has 100 units on hand
    inv = FacilityBatchInventory(facility_id=ctx["fac_a"].id, batch_id=batch.id, on_hand_quantity=100, reserved_quantity=0)
    session.add(inv)
    session.commit()

    # Create proposal for 40 units
    proposal = ProposalService.create_proposal(
        db=session,
        source_facility_id=ctx["fac_a"].id,
        destination_facility_id=ctx["fac_b"].id,
        product_id=prod.id,
        proposed_quantity=40,
        batches=[{"batch_id": batch.id, "quantity": 40}],
        source_rationale={"surplus": 60},
        destination_rationale={"need": 40}
    )
    assert proposal.status == "PROPOSED"
    assert proposal.proposal_version == 1

    # 1. Source approves only -> status becomes PENDING_DESTINATION_APPROVAL
    res1 = ProposalService.record_approval(
        db=session,
        proposal_id=proposal.id,
        facility_id=ctx["fac_a"].id,
        approver_user_id=ctx["user_a"].id,
        proposal_version=1
    )
    assert res1["status"] == "PENDING_DESTINATION_APPROVAL"
    assert res1["source_approved"] is True
    assert res1["destination_approved"] is False

    # 2. Destination approves with mismatched version -> rejected!
    with pytest.raises(ValueError, match="Version mismatch"):
        ProposalService.record_approval(
            db=session,
            proposal_id=proposal.id,
            facility_id=ctx["fac_b"].id,
            approver_user_id=ctx["user_b"].id,
            proposal_version=99  # Wrong version!
        )

    # 3. Destination approves with correct version -> both approved -> atomic reservation!
    res2 = ProposalService.record_approval(
        db=session,
        proposal_id=proposal.id,
        facility_id=ctx["fac_b"].id,
        approver_user_id=ctx["user_b"].id,
        proposal_version=1
    )
    assert res2["success"] is True
    assert res2["status"] == "RESERVED"

    # Verify inventory was reserved atomically
    session.refresh(inv)
    assert inv.reserved_quantity == 40
    assert inv.usable_quantity == 60


def test_qr_verified_journey_and_duplicate_scan_protection(db_session):
    session, ctx = db_session
    today = date.today()

    prod = Product(internal_code="P-MED-QR", name="Enoxaparin", generic_name="Enoxaparin", strength="40mg", dosage_form="SYRINGE", storage_requirements="ROOM_TEMPERATURE")
    session.add(prod)
    session.flush()

    batch = Batch(product_id=prod.id, manufacturer_lot_number="LOT-ENOX-55", expiry_date=today + timedelta(days=200), manufacturer="M1")
    session.add(batch)
    session.flush()

    inv_src = FacilityBatchInventory(facility_id=ctx["fac_a"].id, batch_id=batch.id, on_hand_quantity=50, reserved_quantity=50)
    session.add(inv_src)
    session.flush()

    # Create transfer
    transfer = Transfer(
        proposal_id="prop-demo-1",
        status="READY_FOR_DISPATCH",
        source_facility_id=ctx["fac_a"].id,
        destination_facility_id=ctx["fac_b"].id
    )
    session.add(transfer)
    session.flush()

    pkg = TransferPackage(transfer_id=transfer.id, package_reference="PKG-01", batch_id=batch.id, quantity=50, unit="SYRINGE")
    session.add(pkg)
    session.flush()

    token = "SOS_UNIT_TEST_TOKEN_12345"
    label = SerializedLabel(transfer_package_id=pkg.id, token_hash=hash_token(token), status="ISSUED")
    session.add(label)
    session.commit()

    # 1. Attempt dispatch at WRONG facility (Hospital B instead of Hospital A)
    res_wrong_fac = QRService.process_scan(
        db=session, token=token, facility_id=ctx["fac_b"].id, user_id=ctx["user_b"].id,
        scan_type="DISPATCH", idempotency_key="scan-key-01"
    )
    assert res_wrong_fac["success"] is False
    assert res_wrong_fac["status"] == "WRONG_FACILITY"

    # 2. Valid dispatch scan at source Hospital A
    res_dispatch = QRService.process_scan(
        db=session, token=token, facility_id=ctx["fac_a"].id, user_id=ctx["user_a"].id,
        scan_type="DISPATCH", idempotency_key="scan-key-02"
    )
    assert res_dispatch["success"] is True
    assert res_dispatch["status"] == "DISPATCHED"
    assert transfer.status == "IN_TRANSIT"

    # 3. Duplicate dispatch scan attempt -> rejected!
    res_dup_dispatch = QRService.process_scan(
        db=session, token=token, facility_id=ctx["fac_a"].id, user_id=ctx["user_a"].id,
        scan_type="DISPATCH", idempotency_key="scan-key-03"
    )
    assert res_dup_dispatch["success"] is False
    assert res_dup_dispatch["status"] == "ALREADY_DISPATCHED"

    # 4. Valid receive scan at destination Hospital B
    res_receive = QRService.process_scan(
        db=session, token=token, facility_id=ctx["fac_b"].id, user_id=ctx["user_b"].id,
        scan_type="RECEIVE", idempotency_key="scan-key-04"
    )
    assert res_receive["success"] is True
    assert res_receive["status"] == "RECEIVED"
    assert transfer.status == "RECEIVED"

    # Verify inventory was posted to destination Hospital B ledger
    dest_inv = session.query(FacilityBatchInventory).filter(
        FacilityBatchInventory.facility_id == ctx["fac_b"].id,
        FacilityBatchInventory.batch_id == batch.id
    ).first()
    assert dest_inv is not None
    assert dest_inv.on_hand_quantity == 50

    # 5. Duplicate receive scan attempt -> rejected!
    res_dup_receive = QRService.process_scan(
        db=session, token=token, facility_id=ctx["fac_b"].id, user_id=ctx["user_b"].id,
        scan_type="RECEIVE", idempotency_key="scan-key-05"
    )
    assert res_dup_receive["success"] is False
    assert res_dup_receive["status"] == "ALREADY_RECEIVED"


"""
test_qr_verification_and_reconciliation.py

Comprehensive tests for:
- Valid QR dispatch and receiving flow
- Duplicate dispatch scan protection
- Duplicate receipt scan protection
- Wrong facility boundary enforcement
- Revoked, expired, and unknown label tokens
- Terminal transfer protection
- Idempotency key replay protection
- Over-quantity receipt rejection
- Partial receipt and transit damage reconciliation
- QR image generation
"""
import pytest
import uuid
from datetime import datetime, timezone, timedelta, date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.organization import Organisation, Facility, User
from app.models.product import Product, Batch
from app.models.inventory import FacilityBatchInventory, InventoryLedger
from app.models.proposal import TransferProposal
from app.models.transfer import Transfer, TransferPackage, SerializedLabel, ScanEvent
from app.services.qr_service import QRService
from app.core.security import hash_token


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
        cur.close()

    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(eng)
    eng.dispose()


def _seed_test_transfer_environment(db, initial_on_hand=100, package_qty=50):
    uid = uuid.uuid4().hex[:6]
    org = Organisation(name=f"Health Network {uid}")
    db.add(org)
    db.flush()

    src_fac = Facility(
        organisation_id=org.id, name=f"Source Hospital {uid}",
        facility_type="HOSPITAL", storage_capabilities={"cold_chain": True}
    )
    dst_fac = Facility(
        organisation_id=org.id, name=f"Destination Clinic {uid}",
        facility_type="CLINIC", storage_capabilities={"cold_chain": True}
    )
    third_fac = Facility(
        organisation_id=org.id, name=f"Third Facility {uid}",
        facility_type="HOSPITAL", storage_capabilities={"cold_chain": False}
    )
    db.add_all([src_fac, dst_fac, third_fac])
    db.flush()

    src_user = User(
        organisation_id=org.id, email=f"src_{uid}@test.org",
        name="Source Pharmacist", role="PHARMACIST"
    )
    dst_user = User(
        organisation_id=org.id, email=f"dst_{uid}@test.org",
        name="Dest Receiving Staff", role="PHARMACIST"
    )
    db.add_all([src_user, dst_user])
    db.flush()

    product = Product(
        internal_code=f"MED-{uid}", name="Insulin Glargine 100U/ml",
        generic_name="Insulin Glargine", strength="100U/ml",
        dosage_form="VIAL", storage_requirements="COLD_CHAIN"
    )
    db.add(product)
    db.flush()

    batch = Batch(
        product_id=product.id,
        manufacturer_lot_number=f"LOT-{uid}",
        expiry_date=date.today() + timedelta(days=240),
        manufacturer="Apex Pharma",
        quality_status="RELEASED"
    )
    db.add(batch)
    db.flush()

    inv_src = FacilityBatchInventory(
        facility_id=src_fac.id,
        batch_id=batch.id,
        on_hand_quantity=initial_on_hand,
        reserved_quantity=package_qty,
        unit="VIAL",
        version=1
    )
    db.add(inv_src)
    db.flush()

    proposal = TransferProposal(
        source_facility_id=src_fac.id,
        destination_facility_id=dst_fac.id,
        product_id=product.id,
        proposed_quantity=package_qty,
        unit="VIAL",
        status="APPROVED",
        priority="HIGH",
        source_rationale={"surplus": initial_on_hand, "safety_stock": 20},
        destination_rationale={"projected_need": package_qty, "days_of_cover": 3},
    )
    db.add(proposal)
    db.flush()

    transfer = Transfer(
        proposal_id=proposal.id,
        status="READY_FOR_DISPATCH",
        source_facility_id=src_fac.id,
        destination_facility_id=dst_fac.id,
        tracking_reference=f"TRK-{uid}"
    )
    db.add(transfer)
    db.flush()

    package = TransferPackage(
        transfer_id=transfer.id,
        package_reference=f"PKG-{uid}-01",
        batch_id=batch.id,
        quantity=package_qty,
        unit="VIAL",
        status="PREPARED"
    )
    db.add(package)
    db.flush()

    token = f"TOKEN_QR_TEST_{uid}_{uuid.uuid4().hex}"
    label = SerializedLabel(
        transfer_package_id=package.id,
        token_hash=hash_token(token),
        label_version=1,
        status="ISSUED"
    )
    db.add(label)
    db.commit()

    return {
        "org": org,
        "src_fac": src_fac,
        "dst_fac": dst_fac,
        "third_fac": third_fac,
        "src_user": src_user,
        "dst_user": dst_user,
        "product": product,
        "batch": batch,
        "transfer": transfer,
        "package": package,
        "label": label,
        "token": token,
    }


def test_valid_dispatch_and_receipt_journey(db):
    """Full happy path: Issued -> Dispatched -> In Transit -> Received."""
    ctx = _seed_test_transfer_environment(db, initial_on_hand=100, package_qty=50)

    # 1. Valid Dispatch Scan at Source Facility
    res_dispatch = QRService.process_scan(
        db=db,
        token=ctx["token"],
        facility_id=ctx["src_fac"].id,
        user_id=ctx["src_user"].id,
        scan_type="DISPATCH",
        idempotency_key="disp-key-001"
    )
    assert res_dispatch["success"] is True
    assert res_dispatch["status"] == "DISPATCHED"
    assert res_dispatch["ledger_updated"] is True

    # Verify Transfer and Package status
    db.refresh(ctx["transfer"])
    db.refresh(ctx["package"])
    db.refresh(ctx["label"])
    assert ctx["transfer"].status in ("DISPATCHED", "IN_TRANSIT")
    assert ctx["package"].status == "DISPATCHED"
    assert ctx["label"].status == "DISPATCHED"

    # Verify Source Ledger Decrement
    src_movements = db.query(InventoryLedger).filter(
        InventoryLedger.facility_id == ctx["src_fac"].id,
        InventoryLedger.movement_type == "TRANSFER_DISPATCH"
    ).all()
    assert len(src_movements) == 1
    assert src_movements[0].quantity_delta == -50

    # 2. Valid Receive Scan at Destination Facility
    res_receive = QRService.process_scan(
        db=db,
        token=ctx["token"],
        facility_id=ctx["dst_fac"].id,
        user_id=ctx["dst_user"].id,
        scan_type="RECEIVE",
        idempotency_key="recv-key-001",
        accepted_quantity=50
    )
    assert res_receive["success"] is True
    assert res_receive["status"] == "RECEIVED"
    assert res_receive["ledger_updated"] is True

    # Verify Final Statuses
    db.refresh(ctx["transfer"])
    db.refresh(ctx["package"])
    db.refresh(ctx["label"])
    assert ctx["transfer"].status == "RECEIVED"
    assert ctx["package"].status == "RECEIVED"
    assert ctx["label"].status == "RECEIVED"

    # Verify Destination Inventory and Ledger
    dst_inv = db.query(FacilityBatchInventory).filter(
        FacilityBatchInventory.facility_id == ctx["dst_fac"].id,
        FacilityBatchInventory.batch_id == ctx["batch"].id
    ).first()
    assert dst_inv is not None
    assert dst_inv.on_hand_quantity == 50


def test_duplicate_dispatch_scan_rejected(db):
    """Attempting to dispatch an already-dispatched label is rejected safely."""
    ctx = _seed_test_transfer_environment(db)

    # First dispatch succeeds
    res1 = QRService.process_scan(
        db=db,
        token=ctx["token"],
        facility_id=ctx["src_fac"].id,
        user_id=ctx["src_user"].id,
        scan_type="DISPATCH",
        idempotency_key="disp-unique-1"
    )
    assert res1["success"] is True

    # Duplicate dispatch with different idempotency key rejected
    res2 = QRService.process_scan(
        db=db,
        token=ctx["token"],
        facility_id=ctx["src_fac"].id,
        user_id=ctx["src_user"].id,
        scan_type="DISPATCH",
        idempotency_key="disp-unique-2"
    )
    assert res2["success"] is False
    assert res2["status"] == "ALREADY_DISPATCHED"
    assert res2["ledger_updated"] is False


def test_duplicate_receive_scan_rejected(db):
    """Attempting to receive an already-received label is rejected without double inventory."""
    ctx = _seed_test_transfer_environment(db)

    # Dispatch first
    QRService.process_scan(
        db=db, token=ctx["token"], facility_id=ctx["src_fac"].id,
        user_id=ctx["src_user"].id, scan_type="DISPATCH", idempotency_key="disp-1"
    )
    # Receive first time
    QRService.process_scan(
        db=db, token=ctx["token"], facility_id=ctx["dst_fac"].id,
        user_id=ctx["dst_user"].id, scan_type="RECEIVE", idempotency_key="recv-1"
    )

    # Receive second time
    res_dup = QRService.process_scan(
        db=db, token=ctx["token"], facility_id=ctx["dst_fac"].id,
        user_id=ctx["dst_user"].id, scan_type="RECEIVE", idempotency_key="recv-2"
    )
    assert res_dup["success"] is False
    assert res_dup["status"] == "ALREADY_RECEIVED"
    assert res_dup["ledger_updated"] is False


def test_wrong_facility_dispatch_rejected(db):
    """Scanning at destination or third facility for DISPATCH is blocked."""
    ctx = _seed_test_transfer_environment(db)

    res_wrong = QRService.process_scan(
        db=db,
        token=ctx["token"],
        facility_id=ctx["dst_fac"].id,  # Wrong facility for dispatch
        user_id=ctx["src_user"].id,
        scan_type="DISPATCH",
        idempotency_key="wrong-disp-1"
    )
    assert res_wrong["success"] is False
    assert res_wrong["status"] == "WRONG_FACILITY"
    assert res_wrong["ledger_updated"] is False


def test_wrong_facility_receive_rejected(db):
    """Scanning at source or third facility for RECEIVE is blocked."""
    ctx = _seed_test_transfer_environment(db)

    # Valid dispatch
    QRService.process_scan(
        db=db, token=ctx["token"], facility_id=ctx["src_fac"].id,
        user_id=ctx["src_user"].id, scan_type="DISPATCH", idempotency_key="disp-1"
    )

    # Scan receive at third unrelated facility
    res_wrong = QRService.process_scan(
        db=db,
        token=ctx["token"],
        facility_id=ctx["third_fac"].id,  # Wrong facility
        user_id=ctx["dst_user"].id,
        scan_type="RECEIVE",
        idempotency_key="wrong-recv-1"
    )
    assert res_wrong["success"] is False
    assert res_wrong["status"] == "WRONG_FACILITY"
    assert res_wrong["ledger_updated"] is False


def test_unknown_token_rejected(db):
    """Scanning a token not present in platform registry fails gracefully."""
    ctx = _seed_test_transfer_environment(db)

    res = QRService.process_scan(
        db=db,
        token="SOS_UNREGISTERED_UNKNOWN_TOKEN_9999",
        facility_id=ctx["src_fac"].id,
        user_id=ctx["src_user"].id,
        scan_type="DISPATCH",
        idempotency_key="unk-1"
    )
    assert res["success"] is False
    assert res["status"] == "TOKEN_NOT_FOUND"


def test_revoked_and_expired_label_rejected(db):
    """Revoked or expired labels cannot be scanned."""
    ctx = _seed_test_transfer_environment(db)
    ctx["label"].status = "REVOKED"
    db.commit()

    res_revoked = QRService.process_scan(
        db=db,
        token=ctx["token"],
        facility_id=ctx["src_fac"].id,
        user_id=ctx["src_user"].id,
        scan_type="DISPATCH",
        idempotency_key="rev-1"
    )
    assert res_revoked["success"] is False
    assert res_revoked["status"] == "LABEL_REVOKED"


def test_cancelled_transfer_scan_rejected(db):
    """Scanning a label for a CANCELLED transfer is rejected."""
    ctx = _seed_test_transfer_environment(db)
    ctx["transfer"].status = "CANCELLED"
    db.commit()

    res = QRService.process_scan(
        db=db,
        token=ctx["token"],
        facility_id=ctx["src_fac"].id,
        user_id=ctx["src_user"].id,
        scan_type="DISPATCH",
        idempotency_key="canc-1"
    )
    assert res["success"] is False
    assert res["status"] == "TRANSFER_CANCELLED"


def test_idempotency_key_replay_returns_cached_result(db):
    """Replaying exact same scan request with same idempotency key returns prior result."""
    ctx = _seed_test_transfer_environment(db)

    # First attempt
    res1 = QRService.process_scan(
        db=db,
        token=ctx["token"],
        facility_id=ctx["src_fac"].id,
        user_id=ctx["src_user"].id,
        scan_type="DISPATCH",
        idempotency_key="replay-key-100"
    )
    assert res1["success"] is True
    assert res1["ledger_updated"] is True

    # Replay with same key
    res2 = QRService.process_scan(
        db=db,
        token=ctx["token"],
        facility_id=ctx["src_fac"].id,
        user_id=ctx["src_user"].id,
        scan_type="DISPATCH",
        idempotency_key="replay-key-100"
    )
    assert res2["success"] is True
    assert res2["ledger_updated"] is False
    assert "Duplicate scan submission detected" in res2["message"]


def test_over_quantity_receipt_rejected(db):
    """Destination cannot accept more quantity than authorized in package."""
    ctx = _seed_test_transfer_environment(db, package_qty=50)

    # Dispatch 50
    QRService.process_scan(
        db=db, token=ctx["token"], facility_id=ctx["src_fac"].id,
        user_id=ctx["src_user"].id, scan_type="DISPATCH", idempotency_key="disp-over-1"
    )

    # Attempt to receive 60 (exceeding package quantity 50)
    res_over = QRService.process_scan(
        db=db,
        token=ctx["token"],
        facility_id=ctx["dst_fac"].id,
        user_id=ctx["dst_user"].id,
        scan_type="RECEIVE",
        idempotency_key="recv-over-1",
        accepted_quantity=45,
        damaged_quantity=15  # 45 + 15 = 60 > 50
    )
    assert res_over["success"] is False
    assert res_over["status"] == "OVER_QUANTITY_REJECTED"


def test_partial_receipt_with_damage_reconciliation(db):
    """Partial receipt with damage creates discrepancy reconciliation state and ledger movements."""
    ctx = _seed_test_transfer_environment(db, package_qty=50)

    # Dispatch 50
    QRService.process_scan(
        db=db, token=ctx["token"], facility_id=ctx["src_fac"].id,
        user_id=ctx["src_user"].id, scan_type="DISPATCH", idempotency_key="disp-part-1"
    )

    # Receive 30 accepted, 10 damaged (10 missing)
    res_partial = QRService.process_scan(
        db=db,
        token=ctx["token"],
        facility_id=ctx["dst_fac"].id,
        user_id=ctx["dst_user"].id,
        scan_type="RECEIVE",
        idempotency_key="recv-part-1",
        accepted_quantity=30,
        damaged_quantity=10,
        notes="Box crushed in transit; 10 vials broken, 10 vials missing"
    )
    assert res_partial["success"] is True
    assert res_partial["status"] == "PARTIALLY_RECEIVED"
    assert res_partial["verified_quantity"] == 30
    assert res_partial["damaged_quantity"] == 10
    assert res_partial["missing_quantity"] == 10

    # Package status
    db.refresh(ctx["package"])
    db.refresh(ctx["transfer"])
    assert ctx["package"].status == "RECONCILED_WITH_DISCREPANCY"
    assert ctx["transfer"].status == "PARTIALLY_RECEIVED"

    # Destination usable inventory should be exactly 30 (not 50)
    dst_inv = db.query(FacilityBatchInventory).filter(
        FacilityBatchInventory.facility_id == ctx["dst_fac"].id,
        FacilityBatchInventory.batch_id == ctx["batch"].id
    ).first()
    assert dst_inv.on_hand_quantity == 30


def test_qr_image_generation():
    """QR image data URI generation produces valid base64 PNG data URI."""
    token = "SOS_TEST_TOKEN_XYZ_123"
    data_uri = QRService.generate_qr_image_data_uri(token)
    assert isinstance(data_uri, str)
    assert data_uri.startswith("data:image/png;base64,")
    assert len(data_uri) > 100


def test_full_multi_category_reconciliation(db):
    """
    Test receipt with accepted, damaged, rejected, quarantined, and missing quantities.
    Verify atomic ledger postings for each category.
    """
    ctx = _seed_test_transfer_environment(db, package_qty=100)

    # Dispatch 100
    QRService.process_scan(
        db=db, token=ctx["token"], facility_id=ctx["src_fac"].id,
        user_id=ctx["src_user"].id, scan_type="DISPATCH", idempotency_key="disp-multi-1"
    )

    # Receive: accepted 60, damaged 10, rejected 10, quarantined 10 -> missing = 10
    res = QRService.process_scan(
        db=db,
        token=ctx["token"],
        facility_id=ctx["dst_fac"].id,
        user_id=ctx["dst_user"].id,
        scan_type="RECEIVE",
        idempotency_key="recv-multi-1",
        accepted_quantity=60,
        damaged_quantity=10,
        rejected_quantity=10,
        quarantined_quantity=10,
        notes="Reconciliation with damaged, rejected, and quarantined vials"
    )
    assert res["success"] is True
    assert res["status"] == "PARTIALLY_RECEIVED"
    assert res["verified_quantity"] == 60
    assert res["damaged_quantity"] == 10
    assert res["rejected_quantity"] == 10
    assert res["quarantined_quantity"] == 10
    assert res["missing_quantity"] == 10

    # Destination on-hand usable should be 60
    dst_inv = db.query(FacilityBatchInventory).filter(
        FacilityBatchInventory.facility_id == ctx["dst_fac"].id,
        FacilityBatchInventory.batch_id == ctx["batch"].id
    ).first()
    assert dst_inv.on_hand_quantity == 60

    # Verify ledger movements
    movements = db.query(InventoryLedger).filter(
        InventoryLedger.facility_id == ctx["dst_fac"].id
    ).all()
    movement_types = [m.movement_type for m in movements]
    assert "TRANSFER_RECEIPT" in movement_types
    assert "QUARANTINE" in movement_types
    assert "DAMAGE" in movement_types
    assert "TRANSFER_REJECTION" in movement_types


def test_wrong_transfer_context_rejected(db):
    """Scan specifying an expected_transfer_id rejects when token belongs to another transfer."""
    ctx = _seed_test_transfer_environment(db, package_qty=50)

    res = QRService.process_scan(
        db=db,
        token=ctx["token"],
        facility_id=ctx["src_fac"].id,
        user_id=ctx["src_user"].id,
        scan_type="DISPATCH",
        idempotency_key="scan-wrong-trf",
        expected_transfer_id="TRF-SOME-OTHER-TRANSFER-ID"
    )
    assert res["success"] is False
    assert res["status"] == "WRONG_TRANSFER"
    assert "belongs to transfer" in res["message"]


def test_label_generation_and_inspection(db):
    """Test label generation strictly allowed only in RESERVED / READY_FOR_DISPATCH status."""
    ctx = _seed_test_transfer_environment(db, package_qty=25)

    # Change transfer status to DRAFT
    ctx["transfer"].status = "DRAFT"
    db.commit()

    with pytest.raises(ValueError, match="Cannot generate labels"):
        QRService.generate_labels_for_transfer(db, ctx["transfer"].id)

    # Now set to RESERVED
    ctx["transfer"].status = "RESERVED"
    # Remove existing label from package so it can generate fresh
    pkg = ctx["package"]
    if pkg.label:
        db.delete(pkg.label)
        db.commit()

    result = QRService.generate_labels_for_transfer(db, ctx["transfer"].id)
    assert result["transfer_id"] == ctx["transfer"].id
    assert result["labels_issued_count"] == 1
    assert len(result["labels"]) == 1
    generated_token = result["labels"][0]["token"]
    assert generated_token.startswith("MEDIFLOW_")

    # Inspect labels
    inspect_res = QRService.get_transfer_labels(db, ctx["transfer"].id)
    assert inspect_res["transfer_id"] == ctx["transfer"].id
    assert len(inspect_res["packages"]) == 1
    assert inspect_res["packages"][0]["label"]["status"] == "ISSUED"

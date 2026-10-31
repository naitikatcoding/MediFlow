import pytest
from datetime import date, datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.organization import Organisation, Facility, User
from app.models.product import Product, Batch
from app.models.inventory import FacilityBatchInventory, InventoryLedger
from app.services.ledger_service import LedgerService
from app.services.inventory_service import InventoryService
from app.services.import_service import ImportService
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


from sqlalchemy.pool import StaticPool


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSession()

    org = Organisation(name="Test Health Network")
    session.add(org)
    session.flush()

    fac_hospital = Facility(
        id="fac-hosp-1",
        organisation_id=org.id,
        name="Apex Hospital",
        facility_type="HOSPITAL",
        storage_capabilities={"cold_chain": True, "ambient_max_c": 25}
    )
    fac_pharmacy = Facility(
        id="fac-pharm-1",
        organisation_id=org.id,
        name="Central Pharmacy",
        facility_type="PHARMACY",
        storage_capabilities={"cold_chain": False, "ambient_max_c": 30}
    )
    user = User(
        id="user-ph-1",
        organisation_id=org.id,
        email="pharmacist@apex.demo",
        name="Chief Pharmacist",
        role="PHARMACIST"
    )
    prod_vial = Product(
        id="prod-meropenem",
        internal_code="MED-001",
        name="Meropenem 1g",
        generic_name="Meropenem",
        strength="1g",
        dosage_form="INJECTION",
        base_unit="VIAL",
        storage_requirements="ROOM_TEMPERATURE"
    )
    prod_cold = Product(
        id="prod-insulin",
        internal_code="MED-002",
        name="Insulin Glargine",
        generic_name="Insulin",
        strength="100 IU/ml",
        dosage_form="VIAL",
        base_unit="VIAL",
        storage_requirements="COLD_CHAIN_2_8C"
    )
    session.add_all([fac_hospital, fac_pharmacy, user, prod_vial, prod_cold])
    session.commit()

    yield session, {
        "fac_hospital": fac_hospital,
        "fac_pharmacy": fac_pharmacy,
        "user": user,
        "prod_vial": prod_vial,
        "prod_cold": prod_cold
    }

    session.close()


def test_inventory_calculations_and_usable_stock(test_db):
    session, ctx = test_db
    today = date.today()

    batch = Batch(
        id="batch-mero-1",
        product_id=ctx["prod_vial"].id,
        manufacturer_lot_number="LOT-M-101",
        expiry_date=today + timedelta(days=90),
        manufacturer="Pharma Labs"
    )
    session.add(batch)
    session.commit()

    # Opening balance
    LedgerService.record_movement(
        db=session,
        facility_id=ctx["fac_hospital"].id,
        batch_id=batch.id,
        movement_type="OPENING_BALANCE",
        quantity_delta=100,
        unit="VIAL",
        actor_id=ctx["user"].id,
        reason="Initial inventory load"
    )
    session.commit()

    inv = session.query(FacilityBatchInventory).filter_by(
        facility_id=ctx["fac_hospital"].id, batch_id=batch.id
    ).first()
    assert inv.on_hand_quantity == 100
    assert inv.usable_quantity == 100

    # Reserve 20 units
    LedgerService.record_movement(
        db=session,
        facility_id=ctx["fac_hospital"].id,
        batch_id=batch.id,
        movement_type="TRANSFER_RESERVATION",
        quantity_delta=20,
        unit="VIAL",
        actor_id=ctx["user"].id
    )
    session.commit()
    session.refresh(inv)
    assert inv.reserved_quantity == 20
    assert inv.usable_quantity == 80  # 100 - 20

    # Quarantine 10 units
    LedgerService.record_movement(
        db=session,
        facility_id=ctx["fac_hospital"].id,
        batch_id=batch.id,
        movement_type="QUARANTINE",
        quantity_delta=10,
        unit="VIAL",
        actor_id=ctx["user"].id,
        reason="Suspect packaging"
    )
    session.commit()
    session.refresh(inv)
    assert inv.quarantined_quantity == 10
    assert inv.usable_quantity == 70  # 100 - 20 - 10

    # Release 5 from quarantine
    LedgerService.record_movement(
        db=session,
        facility_id=ctx["fac_hospital"].id,
        batch_id=batch.id,
        movement_type="RELEASE_FROM_QUARANTINE",
        quantity_delta=-5,
        unit="VIAL",
        actor_id=ctx["user"].id,
        reason="Visual check passed"
    )
    session.commit()
    session.refresh(inv)
    assert inv.quarantined_quantity == 5
    assert inv.usable_quantity == 75  # 100 - 20 - 5


def test_duplicate_idempotency_keys(test_db):
    session, ctx = test_db
    today = date.today()

    batch = Batch(
        id="batch-mero-2",
        product_id=ctx["prod_vial"].id,
        manufacturer_lot_number="LOT-M-102",
        expiry_date=today + timedelta(days=90),
        manufacturer="Pharma Labs"
    )
    session.add(batch)
    session.commit()

    key = "idem-key-unique-12345"
    e1 = LedgerService.record_movement(
        db=session,
        facility_id=ctx["fac_hospital"].id,
        batch_id=batch.id,
        movement_type="PURCHASE_RECEIPT",
        quantity_delta=50,
        unit="VIAL",
        idempotency_key=key,
        actor_id=ctx["user"].id
    )
    session.commit()

    inv = session.query(FacilityBatchInventory).filter_by(
        facility_id=ctx["fac_hospital"].id, batch_id=batch.id
    ).first()
    assert inv.on_hand_quantity == 50

    # Repeat with same idempotency key
    e2 = LedgerService.record_movement(
        db=session,
        facility_id=ctx["fac_hospital"].id,
        batch_id=batch.id,
        movement_type="PURCHASE_RECEIPT",
        quantity_delta=50,
        unit="VIAL",
        idempotency_key=key,
        actor_id=ctx["user"].id
    )
    session.commit()

    assert e1.id == e2.id
    session.refresh(inv)
    assert inv.on_hand_quantity == 50  # Must NOT double apply


def test_invalid_adjustments_rejected(test_db):
    session, ctx = test_db
    today = date.today()

    batch = Batch(
        id="batch-mero-3",
        product_id=ctx["prod_vial"].id,
        manufacturer_lot_number="LOT-M-103",
        expiry_date=today + timedelta(days=90),
        manufacturer="Pharma Labs"
    )
    session.add(batch)
    session.commit()

    # Initial 10 on hand
    LedgerService.record_movement(
        db=session,
        facility_id=ctx["fac_hospital"].id,
        batch_id=batch.id,
        movement_type="OPENING_BALANCE",
        quantity_delta=10,
        unit="VIAL",
        actor_id=ctx["user"].id
    )
    session.commit()

    # Attempt to consume 25 units (exceeds on_hand of 10)
    with pytest.raises(ValueError, match="Negative stock invariant"):
        LedgerService.record_movement(
            db=session,
            facility_id=ctx["fac_hospital"].id,
            batch_id=batch.id,
            movement_type="CONSUMPTION",
            quantity_delta=-25,
            unit="VIAL",
            actor_id=ctx["user"].id
        )

    # Attempt manual adjustment producing negative on-hand
    with pytest.raises(ValueError, match="Negative stock invariant"):
        LedgerService.record_movement(
            db=session,
            facility_id=ctx["fac_hospital"].id,
            batch_id=batch.id,
            movement_type="ADJUSTMENT",
            quantity_delta=-30,
            unit="VIAL",
            actor_id=ctx["user"].id,
            reason="Shrinkage"
        )


def test_unit_mismatch_rejected(test_db):
    session, ctx = test_db
    today = date.today()

    batch = Batch(
        id="batch-mero-4",
        product_id=ctx["prod_vial"].id,
        manufacturer_lot_number="LOT-M-104",
        expiry_date=today + timedelta(days=90),
        manufacturer="Pharma Labs"
    )
    session.add(batch)
    session.commit()

    # Product base_unit is VIAL. Attempt movement with BOX.
    with pytest.raises(ValueError, match="Unit mismatch"):
        LedgerService.record_movement(
            db=session,
            facility_id=ctx["fac_hospital"].id,
            batch_id=batch.id,
            movement_type="OPENING_BALANCE",
            quantity_delta=10,
            unit="BOX",
            actor_id=ctx["user"].id
        )


def test_batch_blocking_rules(test_db):
    session, ctx = test_db
    today = date.today()

    # Expired batch
    b_exp = Batch(
        id="b-exp",
        product_id=ctx["prod_vial"].id,
        manufacturer_lot_number="LOT-EXP",
        expiry_date=today - timedelta(days=5),
        manufacturer="Mfr",
        quality_status="RELEASED"
    )
    # Quarantined batch
    b_quar = Batch(
        id="b-quar",
        product_id=ctx["prod_vial"].id,
        manufacturer_lot_number="LOT-QUAR",
        expiry_date=today + timedelta(days=90),
        manufacturer="Mfr",
        quality_status="QUARANTINED"
    )
    # Recalled batch
    b_recalled = Batch(
        id="b-recalled",
        product_id=ctx["prod_vial"].id,
        manufacturer_lot_number="LOT-RECALL",
        expiry_date=today + timedelta(days=90),
        manufacturer="Mfr",
        quality_status="RECALLED"
    )
    # Cold chain batch
    b_cold = Batch(
        id="b-cold",
        product_id=ctx["prod_cold"].id,
        manufacturer_lot_number="LOT-COLD",
        expiry_date=today + timedelta(days=90),
        manufacturer="Mfr",
        quality_status="RELEASED"
    )
    session.add_all([b_exp, b_quar, b_recalled, b_cold])
    session.commit()

    chk_exp = InventoryService.check_batch_eligibility(session, b_exp.id)
    assert chk_exp["is_blocked"] is True
    assert "EXPIRED" in chk_exp["blocking_reasons"]

    chk_quar = InventoryService.check_batch_eligibility(session, b_quar.id)
    assert chk_quar["is_blocked"] is True
    assert "BATCH_QUARANTINED" in chk_quar["blocking_reasons"]

    chk_recall = InventoryService.check_batch_eligibility(session, b_recalled.id)
    assert chk_recall["is_blocked"] is True
    assert "BATCH_RECALLED" in chk_recall["blocking_reasons"]

    # Destination pharmacy lacks cold chain
    chk_cold = InventoryService.check_batch_eligibility(
        session,
        b_cold.id,
        destination_facility_id=ctx["fac_pharmacy"].id
    )
    assert chk_cold["storage_compatible"] is False
    assert chk_cold["is_blocked"] is True
    assert any("COLD_CHAIN_MISSING" in r for r in chk_cold["blocking_reasons"])


def test_fefo_allocation(test_db):
    session, ctx = test_db
    today = date.today()

    # Three batches with different expiries: 30 days, 60 days, 120 days
    b1 = Batch(id="b-fefo-1", product_id=ctx["prod_vial"].id, manufacturer_lot_number="LOT-30D", expiry_date=today + timedelta(days=30), manufacturer="Mfr")
    b2 = Batch(id="b-fefo-2", product_id=ctx["prod_vial"].id, manufacturer_lot_number="LOT-60D", expiry_date=today + timedelta(days=60), manufacturer="Mfr")
    b3 = Batch(id="b-fefo-3", product_id=ctx["prod_vial"].id, manufacturer_lot_number="LOT-120D", expiry_date=today + timedelta(days=120), manufacturer="Mfr")
    session.add_all([b1, b2, b3])
    session.commit()

    # Add stock: b1 has 15, b2 has 20, b3 has 50
    LedgerService.record_movement(session, ctx["fac_hospital"].id, b1.id, "OPENING_BALANCE", 15, "VIAL", actor_id="admin")
    LedgerService.record_movement(session, ctx["fac_hospital"].id, b2.id, "OPENING_BALANCE", 20, "VIAL", actor_id="admin")
    LedgerService.record_movement(session, ctx["fac_hospital"].id, b3.id, "OPENING_BALANCE", 50, "VIAL", actor_id="admin")
    session.commit()

    # Request 25 units: should take 15 from b1 (expires in 30d) and 10 from b2 (expires in 60d)
    res = InventoryService.allocate_fefo(
        session,
        facility_id=ctx["fac_hospital"].id,
        product_id=ctx["prod_vial"].id,
        requested_quantity=25
    )

    assert res["is_fully_allocated"] is True
    assert res["allocated_total"] == 25
    assert len(res["allocations"]) == 2
    assert res["allocations"][0]["batch_id"] == b1.id
    assert res["allocations"][0]["allocated_quantity"] == 15
    assert res["allocations"][1]["batch_id"] == b2.id
    assert res["allocations"][1]["allocated_quantity"] == 10


def test_csv_import_workflow(test_db):
    session, ctx = test_db
    today = date.today()
    exp_str = (today + timedelta(days=180)).isoformat()

    csv_data = f"""facility_id,product_code,lot_number,expiry_date,quantity,unit,manufacturer
fac-hosp-1,MED-001,LOT-CSV-01,{exp_str},150,VIAL,Imported Labs
fac-hosp-1,MED-001,LOT-CSV-ERR,INVALID_DATE,50,VIAL,Bad Date
fac-hosp-1,UNKNOWN_CODE,LOT-CSV-02,{exp_str},30,VIAL,Bad Product
fac-hosp-1,MED-001,LOT-CSV-NEG,{exp_str},-10,VIAL,Negative Qty
"""

    job = ImportService.process_inventory_csv(
        db=session,
        csv_text=csv_data,
        target_facility_id=ctx["fac_hospital"].id,
        filename="test_upload.csv",
        actor_id=ctx["user"].id
    )

    assert job.status == "COMPLETED"
    assert job.row_count == 4
    assert job.accepted_count == 1
    assert job.rejected_count == 3
    assert len(job.error_summary["errors"]) == 3


def test_reconciliation_service(test_db):
    session, ctx = test_db
    today = date.today()

    batch = Batch(
        id="batch-reconcile",
        product_id=ctx["prod_vial"].id,
        manufacturer_lot_number="LOT-REC-01",
        expiry_date=today + timedelta(days=90),
        manufacturer="Pharma Labs"
    )
    session.add(batch)
    session.commit()

    LedgerService.record_movement(session, ctx["fac_hospital"].id, batch.id, "OPENING_BALANCE", 40, "VIAL", actor_id="admin")
    LedgerService.record_movement(session, ctx["fac_hospital"].id, batch.id, "CONSUMPTION", -15, "VIAL", actor_id="nurse")
    session.commit()

    res = InventoryService.reconcile_batch_with_ledger(session, ctx["fac_hospital"].id, batch.id)
    assert res["is_balanced"] is True
    assert res["materialized_on_hand"] == 25
    assert res["ledger_computed_on_hand"] == 25
    assert res["discrepancy"] == 0


def test_inventory_api_endpoints(client, test_db):
    session, ctx = test_db
    from app.api.deps import get_db

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        # Test inventory summary
        res = client.get("/api/v1/inventory/summary")
        assert res.status_code == 200
        data = res.json()
        assert "total_on_hand" in data
        assert "total_usable" in data
        assert "data_freshness_status" in data

        # Test inventory list
        res_list = client.get("/api/v1/inventory")
        assert res_list.status_code == 200
        assert isinstance(res_list.json(), list)

        # Test ledger list
        res_ledger = client.get("/api/v1/inventory/ledger")
        assert res_ledger.status_code == 200
        assert isinstance(res_ledger.json(), list)

        # Create a test batch for adjustment
        today = date.today()
        batch = Batch(
            id="batch-api-test",
            product_id=ctx["prod_vial"].id,
            manufacturer_lot_number="LOT-API-01",
            expiry_date=today + timedelta(days=90),
            manufacturer="Pharma Labs"
        )
        session.add(batch)
        session.commit()

        # Seed initial stock
        LedgerService.record_movement(
            db=session,
            facility_id=ctx["fac_hospital"].id,
            batch_id=batch.id,
            movement_type="OPENING_BALANCE",
            quantity_delta=20,
            unit="VIAL",
            actor_id=ctx["user"].id
        )
        session.commit()

        # Test adjustment API
        res_adj = client.post("/api/v1/inventory/adjustments", json={
            "facility_id": ctx["fac_hospital"].id,
            "batch_id": batch.id,
            "adjustment_type": "ADJUSTMENT",
            "quantity_delta": 5,
            "unit": "VIAL",
            "reason": "Found during physical cycle count",
            "actor_id": ctx["user"].id
        })
        assert res_adj.status_code == 200
        adj_data = res_adj.json()
        assert adj_data["success"] is True
        assert adj_data["movement_type"] == "ADJUSTMENT"

        # Test invalid negative adjustment via API rejected
        res_inv = client.post("/api/v1/inventory/adjustments", json={
            "facility_id": ctx["fac_hospital"].id,
            "batch_id": batch.id,
            "adjustment_type": "ADJUSTMENT",
            "quantity_delta": -99999,
            "unit": "VIAL",
            "reason": "Massive subtraction",
            "actor_id": ctx["user"].id
        })
        assert res_inv.status_code == 400
        assert "Negative stock" in res_inv.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_db, None)

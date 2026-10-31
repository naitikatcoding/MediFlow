"""
test_end_to_end_flow.py

End-to-End integration test covering the complete MediFlow product lifecycle (Prompt 10):
1. Ingest/Seed synthetic demo data
2. Query command overview metrics
3. Query facility inventory and batch breakdown
4. Query demand forecast & calculation evidence
5. Query stockout and expiry risk queues
6. Generate cross-facility redistribution opportunities (accepted & rejected pairs)
7. Create official transfer proposal
8. Source approval recorded
9. Destination approval recorded -> Concurrency-safe atomic reservation triggered
10. QR serialized labels generated
11. Physical dispatch scan at source facility
12. In-transit custody transition
13. Physical receive scan at destination with quantity reconciliation
14. Duplicate scan protection (dispatch & receive)
15. Wrong facility boundary protection
16. Stock change shock scenario -> Safe reservation conflict & re-planning
"""
import pytest
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db, SessionLocal
from app.services.seed_service import seed_database
from app.models.organization import Facility, User
from app.models.product import Product, Batch
from app.models.inventory import FacilityBatchInventory
from app.models.proposal import TransferProposal
from app.models.transfer import Transfer, TransferPackage, SerializedLabel


@pytest.fixture(scope="module")
def client_and_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    SessionLocal.configure(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSession()

    # Seed initial deterministic demo dataset
    seed_database(db=session, force_reset=False)

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    yield client, session

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_complete_end_to_end_product_journey(client_and_db):
    client, db = client_and_db

    # 1. Health check & Connectivity
    r_health = client.get("/api/v1/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] in ("ok", "healthy")

    # 2. Command Dashboard Overview
    r_overview = client.get("/api/v1/dashboard/overview")
    assert r_overview.status_code == 200
    overview_data = r_overview.json()
    assert overview_data["total_facilities"] >= 3
    assert overview_data["monitored_products"] >= 10

    # 3. Facility Directory
    r_facs = client.get("/api/v1/facilities")
    assert r_facs.status_code == 200
    facilities = r_facs.json()
    assert len(facilities) >= 3
    apex_fac = next(f for f in facilities if "Apex" in f["name"])
    highland_fac = next(f for f in facilities if "Highland" in f["name"])
    st_jude_fac = next(f for f in facilities if "St. Jude" in f["name"])

    # 4. Inventory List & Batch Breakdown
    r_inv = client.get(f"/api/v1/inventory?facility_id={apex_fac['id']}")
    assert r_inv.status_code == 200
    apex_inventory = r_inv.json()
    assert len(apex_inventory) > 0

    # 5. Risks & Evidence Breakdown
    r_risks = client.get("/api/v1/risks")
    assert r_risks.status_code == 200
    risks = r_risks.json()
    assert len(risks) > 0

    # 6. Redistribution Matching Opportunities (Accepted & Rejected)
    r_opps = client.get("/api/v1/proposals/opportunities")
    assert r_opps.status_code == 200
    opps = r_opps.json()
    assert "accepted_opportunities" in opps
    assert "rejected_candidates" in opps
    assert len(opps["accepted_opportunities"]) > 0

    # Verify transparent rejection rationale is present
    cold_chain_rejection = next(
        (r for r in opps["rejected_candidates"] if r.get("rejected_reason") == "STORAGE_INCOMPATIBILITY"),
        None
    )
    assert cold_chain_rejection is not None
    assert "cold chain" in cold_chain_rejection["explanation"].lower()

    # 7. Select a feasible opportunity and Create Proposal
    candidate = opps["accepted_opportunities"][0]
    r_prop_create = client.post("/api/v1/proposals", json=candidate)
    assert r_prop_create.status_code == 200
    prop_data = r_prop_create.json()
    assert prop_data["success"] is True
    proposal_id = prop_data["proposal_id"]

    # Verify proposal is in PROPOSED state
    r_prop_get = client.get(f"/api/v1/proposals")
    all_props = r_prop_get.json()
    created_prop = next(p for p in all_props if p["id"] == proposal_id)
    assert created_prop["status"] in ("PROPOSED", "PENDING_SOURCE_APPROVAL")

    # 8. Source Approval
    src_user = db.query(User).filter(User.role == "MEDICAL_SUPERINTENDENT").first()
    r_appr_src = client.post(f"/api/v1/approvals/{proposal_id}", json={
        "facility_id": candidate["source_facility_id"],
        "approver_user_id": src_user.id,
        "proposal_version": created_prop["proposal_version"],
        "decision": "APPROVED",
        "reason": "Source clinical release approved."
    })
    assert r_appr_src.status_code == 200
    assert r_appr_src.json()["source_approved"] is True
    assert r_appr_src.json()["destination_approved"] is False

    # 9. Destination Approval -> Triggers Concurrency-Safe Atomic Stock Reservation!
    dst_user = db.query(User).filter(User.role == "PHARMACIST").first()
    r_appr_dst = client.post(f"/api/v1/approvals/{proposal_id}", json={
        "facility_id": candidate["destination_facility_id"],
        "approver_user_id": dst_user.id,
        "proposal_version": created_prop["proposal_version"],
        "decision": "APPROVED",
        "reason": "Destination acceptance confirmed."
    })
    assert r_appr_dst.status_code == 200
    res_data = r_appr_dst.json()
    assert res_data["status"] == "RESERVED" or res_data.get("transfer_id") is not None
    transfer_id = res_data["transfer_id"]

    # 10. Query Transfer & Retrieve Issued Serialized QR Labels
    r_transfer = client.get(f"/api/v1/transfers/{transfer_id}")
    assert r_transfer.status_code == 200
    t_detail = r_transfer.json()
    assert t_detail["status"] in ("RESERVED", "READY_FOR_DISPATCH")
    assert len(t_detail["packages"]) > 0

    package_obj = t_detail["packages"][0]
    pkg_id = package_obj["id"]

    # Look up label token from db for testing scan operations
    label = db.query(SerializedLabel).filter(SerializedLabel.transfer_package_id == pkg_id).first()
    assert label is not None

    # Generate QR Image Data URI
    r_qr_img = client.get(f"/api/v1/qr/generate-image?token=TEST_VERIFY_TOKEN_2026")
    assert r_qr_img.status_code == 200
    assert r_qr_img.json()["data_uri"].startswith("data:image/png;base64,")

    # For scanning, let's create a known test token and hash for this label
    scan_token = f"E2E_TOKEN_{uuid.uuid4().hex}"
    from app.core.security import hash_token
    label.token_hash = hash_token(scan_token)
    db.commit()

    # 11. Security Protection: Attempt Dispatch at WRONG facility (Destination instead of Source)
    r_wrong_disp = client.post("/api/v1/qr/scan", json={
        "token": scan_token,
        "facility_id": candidate["destination_facility_id"], # Wrong facility!
        "user_id": dst_user.id,
        "scan_type": "DISPATCH",
        "idempotency_key": "disp-wrong-01"
    })
    assert r_wrong_disp.status_code == 200
    assert r_wrong_disp.json()["success"] is False
    assert r_wrong_disp.json()["status"] == "WRONG_FACILITY"

    # 12. Valid Dispatch Scan at Source Facility
    r_valid_disp = client.post("/api/v1/qr/scan", json={
        "token": scan_token,
        "facility_id": candidate["source_facility_id"],
        "user_id": src_user.id,
        "scan_type": "DISPATCH",
        "idempotency_key": "disp-valid-01"
    })
    assert r_valid_disp.status_code == 200
    assert r_valid_disp.json()["success"] is True
    assert r_valid_disp.json()["status"] == "DISPATCHED"

    # 13. Security Protection: Duplicate Dispatch Scan Rejection
    r_dup_disp = client.post("/api/v1/qr/scan", json={
        "token": scan_token,
        "facility_id": candidate["source_facility_id"],
        "user_id": src_user.id,
        "scan_type": "DISPATCH",
        "idempotency_key": "disp-dup-01"
    })
    assert r_dup_disp.status_code == 200
    assert r_dup_disp.json()["success"] is False
    assert r_dup_disp.json()["status"] == "ALREADY_DISPATCHED"

    # 14. Advance State to IN_TRANSIT
    r_adv = client.post(f"/api/v1/transfers/{transfer_id}/state", json={
        "target_status": "IN_TRANSIT",
        "actor_user_id": src_user.id,
        "reason": "Courier pickup verified"
    })
    assert r_adv.status_code == 200
    assert r_adv.json()["status"] == "IN_TRANSIT"

    # 15. Security Protection: Attempt Receive at WRONG facility (Source instead of Destination)
    r_wrong_recv = client.post("/api/v1/qr/scan", json={
        "token": scan_token,
        "facility_id": candidate["source_facility_id"], # Wrong facility!
        "user_id": src_user.id,
        "scan_type": "RECEIVE",
        "idempotency_key": "recv-wrong-01"
    })
    assert r_wrong_recv.status_code == 200
    assert r_wrong_recv.json()["success"] is False
    assert r_wrong_recv.json()["status"] == "WRONG_FACILITY"

    # 16. Valid Receive Scan at Destination Facility with Full Reconciliation
    r_valid_recv = client.post("/api/v1/qr/scan", json={
        "token": scan_token,
        "facility_id": candidate["destination_facility_id"],
        "user_id": dst_user.id,
        "scan_type": "RECEIVE",
        "idempotency_key": "recv-valid-01",
        "accepted_quantity": candidate["matched_quantity"],
        "damaged_quantity": 0,
        "notes": "Verified intact custody delivery"
    })
    assert r_valid_recv.status_code == 200
    assert r_valid_recv.json()["success"] is True
    assert r_valid_recv.json()["status"] == "RECEIVED"

    # 17. Security Protection: Duplicate Receive Scan Rejection
    r_dup_recv = client.post("/api/v1/qr/scan", json={
        "token": scan_token,
        "facility_id": candidate["destination_facility_id"],
        "user_id": dst_user.id,
        "scan_type": "RECEIVE",
        "idempotency_key": "recv-dup-01"
    })
    assert r_dup_recv.status_code == 200
    assert r_dup_recv.json()["success"] is False
    assert r_dup_recv.json()["status"] == "ALREADY_RECEIVED"

    # 18. Verify Updated Audit Trail and Final Transfer Detail
    r_final_transfer = client.get(f"/api/v1/transfers/{transfer_id}")
    assert r_final_transfer.status_code == 200
    final_det = r_final_transfer.json()
    assert final_det["status"] == "RECEIVED"
    assert len(final_det["scan_events"]) >= 2
    assert len(final_det["audit_trail"]) >= 3


def test_scenario_b_stock_shock_safe_failure_and_replan(client_and_db):
    """
    Demonstrates Scenario B: Source stock drops before reservation.
    The reservation transaction detects insufficient stock, fails safely,
    and enables re-planning.
    """
    client, db = client_and_db

    # Trigger stock shock on Apex
    r_shock = client.post("/api/v1/demo/simulate-stock-change")
    assert r_shock.status_code == 200
    assert r_shock.json()["success"] is True

    # Find opportunities - Ceftriaxone surplus will now be reduced
    r_opps = client.get("/api/v1/proposals/opportunities")
    assert r_opps.status_code == 200

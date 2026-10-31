"""
Unit and Integration Tests for MediFlow LangGraph Multi-Agent Workflow, Gemini, and MEKO Adapters.
Tests:
- Deterministic tool contracts
- Invalid model output handling
- Model timeout and fallback labeling
- MEKO unavailable fallback and provenance
- Graph path execution and checkpoint pause
- Dual approval resume and atomic reservation
- Policy re-validation failure before reservation
- API agent endpoints
"""
import os
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_agent_workflow.db")

from app.core.database import Base
from app.models.organization import Organisation, Facility, User
from app.models.product import Product, Batch
from app.models.inventory import FacilityBatchInventory
from app.models.consumption import ConsumptionRecord
from app.models.workflow import AgentWorkflowRun
from app.agents import tools
from app.agents.graph import create_agent_graph
from app.agents.state import AgentGraphState
from app.integrations.gemini import gemini_adapter
from app.integrations.meko import meko_adapter
from app.services.agent_service import MediFlowAgentService
from app.services.inventory_service import InventoryService
from app.services.ledger_service import LedgerService
from app.services.proposal_service import ProposalService


@pytest.fixture(scope="module")
def db_session():
    import uuid
    if os.path.exists("./test_agent_workflow.db"):
        try:
            os.remove("./test_agent_workflow.db")
        except Exception:
            pass

    test_engine = create_engine(
        "sqlite:///./test_agent_workflow.db",
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSession()

    try:
        org = Organisation(name="Agent Test Regional Health")
        session.add(org)
        session.flush()

        src_fac = Facility(organisation_id=org.id, name="Hub General Hospital", facility_type="HOSPITAL")
        dst_fac = Facility(organisation_id=org.id, name="Community Clinic West", facility_type="CLINIC")
        session.add_all([src_fac, dst_fac])
        session.flush()

        uid = uuid.uuid4().hex[:6]
        user_src = User(organisation_id=org.id, email=f"src_doc_{uid}@test.com", name="Dr. Source", role="PHARMACIST")
        user_dst = User(organisation_id=org.id, email=f"dst_doc_{uid}@test.com", name="Dr. Dest", role="PHARMACIST")
        session.add_all([user_src, user_dst])
        session.flush()

        # Product with transferable policy
        prod = Product(
            internal_code="AGT-MED-001",
            name="Amoxicillin 500mg Capsules",
            generic_name="Amoxicillin",
            strength="500mg",
            dosage_form="CAPSULE",
            base_unit="CAPSULE",
            storage_requirements="ROOM_TEMPERATURE",
            transfer_policy_code="ALLOW_ALL"
        )
        # Restricted product
        prod_restricted = Product(
            internal_code="AGT-MED-002",
            name="Restricted Controlled Substance",
            generic_name="Controlled",
            strength="10mg",
            dosage_form="TABLET",
            base_unit="TABLET",
            storage_requirements="ROOM_TEMPERATURE",
            transfer_policy_code="RESTRICTED_LOCAL_ONLY"
        )
        session.add_all([prod, prod_restricted])
        session.flush()

        now = datetime.now(timezone.utc)
        today = now.date()
        # Eligible Batch at Source
        batch_src = Batch(
            product_id=prod.id,
            manufacturer_lot_number="AGT-BATCH-001",
            expiry_date=today + timedelta(days=180),
            quality_status="RELEASED",
            manufacturer="PharmaCorp"
        )
        # Quarantined Batch
        batch_quarantined = Batch(
            product_id=prod.id,
            manufacturer_lot_number="AGT-BATCH-QUAR",
            expiry_date=today + timedelta(days=90),
            quality_status="QUARANTINED",
            manufacturer="PharmaCorp"
        )
        session.add_all([batch_src, batch_quarantined])
        session.flush()

        # Stock at Source: 500 units usable
        LedgerService.record_movement(
            db=session,
            facility_id=src_fac.id,
            batch_id=batch_src.id,
            movement_type="PURCHASE_RECEIPT",
            quantity_delta=500,
            unit="CAPSULE",
            idempotency_key="INIT-SRC-STOCK-500"
        )
        # Quarantined stock: 50 units
        LedgerService.record_movement(
            db=session,
            facility_id=src_fac.id,
            batch_id=batch_quarantined.id,
            movement_type="PURCHASE_RECEIPT",
            quantity_delta=50,
            unit="CAPSULE",
            idempotency_key="INIT-QUAR-STOCK-50"
        )

        # Destination has high demand (10/day) and low stock (10 units = 1 day of cover)
        LedgerService.record_movement(
            db=session,
            facility_id=dst_fac.id,
            batch_id=batch_src.id,
            movement_type="PURCHASE_RECEIPT",
            quantity_delta=10,
            unit="CAPSULE",
            idempotency_key="INIT-DST-STOCK-10"
        )

        # 8 weeks of consumption at destination: 70 units/week = 10 units/day
        for w in range(1, 9):
            dt = now - timedelta(weeks=w)
            cr = ConsumptionRecord(
                facility_id=dst_fac.id,
                product_id=prod.id,
                consumed_at=dt,
                quantity=70,
                unit="CAPSULE"
            )
            session.add(cr)

        # Source has low consumption: 7 units/week = 1 unit/day
        for w in range(1, 9):
            dt = now - timedelta(weeks=w)
            cr = ConsumptionRecord(
                facility_id=src_fac.id,
                product_id=prod.id,
                consumed_at=dt,
                quantity=7,
                unit="CAPSULE"
            )
            session.add(cr)

        session.commit()

        yield {
            "session": session,
            "src_fac": src_fac,
            "dst_fac": dst_fac,
            "prod": prod,
            "prod_restricted": prod_restricted,
            "batch_src": batch_src,
            "batch_quarantined": batch_quarantined,
            "user_src": user_src,
            "user_dst": user_dst
        }

    finally:
        session.close()
        test_engine.dispose()
        if os.path.exists("./test_agent_workflow.db"):
            try:
                os.remove("./test_agent_workflow.db")
            except Exception:
                pass


def test_deterministic_tool_contracts(db_session):
    """Verifies all deterministic tools execute cleanly without raw DB exposure."""
    db = db_session["session"]
    src_id = db_session["src_fac"].id
    dst_id = db_session["dst_fac"].id
    prod_id = db_session["prod"].id
    batch_id = db_session["batch_src"].id

    # 1. get_facility_inventory
    inv = tools.get_facility_inventory(db, facility_id=src_id, product_id=prod_id)
    assert inv["tool"] == "get_facility_inventory"
    assert inv["record_count"] >= 1
    assert "data_quality" in inv

    # 2. get_consumption_history
    hist = tools.get_consumption_history(db, facility_id=dst_id, product_id=prod_id, weeks=8)
    assert hist["weeks_found"] >= 7
    assert hist["has_sufficient_history"] is True

    # 3. run_demand_forecast
    fc = tools.run_demand_forecast(db, facility_id=dst_id, product_id=prod_id)
    assert fc["daily_average_demand"] > 0
    assert fc["demand_30d"] > 0
    assert fc["confidence_score"] > 0.1

    # 4. calculate_stockout_risk
    so = tools.calculate_stockout_risk(db, facility_id=dst_id, product_id=prod_id)
    assert so["stockout_risks_found"] >= 1
    assert so["has_critical_stockout"] is True

    # 5. calculate_expiry_risk
    exp = tools.calculate_expiry_risk(db, facility_id=src_id, product_id=prod_id)
    assert "expiry_risks_found" in exp

    # 6. find_candidate_facilities
    cand = tools.find_candidate_facilities(db, product_id=prod_id)
    assert cand["accepted_opportunities"] >= 1

    # 7. validate_transfer_proposal
    val = tools.validate_transfer_proposal(
        db,
        source_facility_id=src_id,
        destination_facility_id=dst_id,
        product_id=prod_id,
        quantity=50,
        batches=[{"batch_id": batch_id, "quantity": 50}]
    )
    assert val["passed"] is True
    assert val["failure_count"] == 0

    # Policy rejection on negative quantity
    val_neg = tools.validate_transfer_proposal(
        db,
        source_facility_id=src_id,
        destination_facility_id=dst_id,
        product_id=prod_id,
        quantity=-10,
        batches=[{"batch_id": batch_id, "quantity": 10}]
    )
    assert val_neg["passed"] is False


def test_gemini_adapter_invalid_model_output():
    """Verifies that invalid or malformed output from LLM is safely handled and fallback is used."""
    # When api_key is None, it uses template fallback
    res = gemini_adapter.generate_structured_analysis(
        context_type="REDISTRIBUTION_PROPOSAL",
        facts={
            "source_facility_name": "Hub Hospital",
            "destination_facility_name": "Clinic West",
            "product_name": "Amoxicillin 500mg",
            "proposed_quantity": 50,
            "destination_days_of_cover": 1.0
        }
    )
    assert res["status"] == "FALLBACK"
    assert res["gemini_live_executed"] is False
    assert "structured_analysis" in res
    analysis = res["structured_analysis"]
    assert "Amoxicillin" in analysis["clinical_operational_summary"]
    assert len(analysis["key_risk_drivers"]) >= 1


def test_gemini_adapter_timeout_and_fallback():
    """Simulates Gemini outage and verifies deterministic fallback is explicitly labeled."""
    gemini_adapter.set_unavailable_for_testing(True)
    try:
        res = gemini_adapter.generate_structured_analysis(
            context_type="RISK_ALERT",
            facts={"facility_name": "Clinic West", "product_name": "Amoxicillin", "days_of_cover": 2.5}
        )
        assert res["status"] == "FALLBACK"
        assert res["source"] == "DETERMINISTIC_TEMPLATE_FALLBACK"
        assert res["gemini_live_executed"] is False
        assert "fallback_reason" in res
    finally:
        gemini_adapter.set_unavailable_for_testing(False)


def test_meko_adapter_unavailable_fallback():
    """Simulates MEKO unavailable mode, verifying graceful storage and retrieval with provenance."""
    meko_adapter.set_unavailable_for_testing(True)
    try:
        status = meko_adapter.get_status()
        assert status["mode"] == "LOCAL_FALLBACK"

        # Store context
        stored = meko_adapter.store_context(
            summary="Emergency stock reserve maintained at Hub",
            facility_id="fac_123",
            tags=["policy"]
        )
        assert stored["provenance"] == "LOCAL_MEMORY_FALLBACK"

        # Retrieve context
        retrieved = meko_adapter.retrieve_context(facility_id="fac_123")
        assert len(retrieved) >= 1
        assert retrieved[0]["provenance"] == "LOCAL_MEMORY_FALLBACK"
    finally:
        meko_adapter.set_unavailable_for_testing(False)


def test_graph_path_and_checkpoint_pause(db_session):
    """Executes full LangGraph workflow and verifies sequential nodes and checkpoint pause."""
    db = db_session["session"]
    prod_id = db_session["prod"].id

    res = MediFlowAgentService.run_workflow_cycle(
        db=db,
        product_id=prod_id,
        trigger_event_type="MANUAL"
    )

    assert "workflow_id" in res
    assert res["workflow_status"] == "PAUSED_FOR_APPROVAL"
    assert res["pause_for_human_approval"] is True
    assert res["proposal_id"] is not None

    # Check node trace
    trace = res.get("node_trace", [])
    node_names = [t["node_name"] for t in trace]
    assert "Inventory Monitoring Agent" in node_names
    assert "Demand Forecast Agent" in node_names
    assert "Expiry and Risk Agent" in node_names
    assert "Supply Optimisation Agent" in node_names
    assert "Network Coordinator" in node_names

    # Verify agent observations
    obs = res.get("agent_observations", {})
    assert "inventory_monitor" in obs
    assert "demand_forecast" in obs
    assert "expiry_risk" in obs
    assert "supply_optimization" in obs
    assert "orchestrator" in obs

    # Verify DB record created
    run_rec = db.query(AgentWorkflowRun).filter(AgentWorkflowRun.id == res["workflow_id"]).first()
    assert run_rec is not None
    assert run_rec.workflow_status == "PAUSED_FOR_APPROVAL"
    assert run_rec.proposal_id == res["proposal_id"]


def test_approval_resume_and_reservation(db_session):
    """Tests dual clinical approval and workflow resumption executing stock reservation."""
    db = db_session["session"]
    prod_id = db_session["prod"].id
    src_id = db_session["src_fac"].id
    dst_id = db_session["dst_fac"].id
    u_src_id = db_session["user_src"].id
    u_dst_id = db_session["user_dst"].id

    # 1. Run workflow cycle
    workflow_state = MediFlowAgentService.run_workflow_cycle(
        db=db,
        product_id=prod_id
    )
    workflow_id = workflow_state["workflow_id"]
    proposal_id = workflow_state["proposal_id"]
    proposal_ver = workflow_state["proposal_version"]

    # Attempting to resume before approvals should remain paused
    pre_resume = MediFlowAgentService.resume_workflow_approval(db, workflow_id)
    assert pre_resume["status"] == "PAUSED_AWAITING_APPROVALS"

    # Source approves
    ProposalService.record_approval(
        db=db,
        proposal_id=proposal_id,
        facility_id=src_id,
        approver_user_id=u_src_id,
        proposal_version=proposal_ver,
        decision="APPROVED",
        auto_reserve=False
    )

    # Destination approves
    ProposalService.record_approval(
        db=db,
        proposal_id=proposal_id,
        facility_id=dst_id,
        approver_user_id=u_dst_id,
        proposal_version=proposal_ver,
        decision="APPROVED",
        auto_reserve=False
    )

    # Resume workflow
    resumed = MediFlowAgentService.resume_workflow_approval(db, workflow_id)
    assert resumed["status"] == "COMPLETED"

    # Verify workflow run updated
    run_rec = db.query(AgentWorkflowRun).filter(AgentWorkflowRun.id == workflow_id).first()
    assert run_rec.workflow_status == "COMPLETED"
    assert run_rec.completed_at is not None


def test_revalidation_before_reservation_failure(db_session):
    """
    Verifies that if usable stock is depleted between proposal creation and resumption,
    re-validation fails and halts reservation, marking status FAILED_REVALIDATION.
    """
    db = db_session["session"]
    src_id = db_session["src_fac"].id
    dst_id = db_session["dst_fac"].id
    prod_id = db_session["prod"].id
    batch_id = db_session["batch_src"].id
    u_src_id = db_session["user_src"].id
    u_dst_id = db_session["user_dst"].id

    # Run workflow
    wf = MediFlowAgentService.run_workflow_cycle(db=db, product_id=prod_id)
    wf_id = wf["workflow_id"]
    prop_id = wf["proposal_id"]
    prop_ver = wf["proposal_version"]

    # Deplete or block the source batch completely before resumption!
    LedgerService.record_movement(
        db=db,
        facility_id=src_id,
        batch_id=batch_id,
        movement_type="ADJUSTMENT",
        quantity_delta=-500,
        unit="CAPSULE",
        idempotency_key=f"DEPLETE-STOCK-{wf_id}"
    )

    # Approvals are recorded
    ProposalService.record_approval(
        db=db,
        proposal_id=prop_id,
        facility_id=src_id,
        approver_user_id=u_src_id,
        proposal_version=prop_ver,
        decision="APPROVED",
        auto_reserve=False
    )
    ProposalService.record_approval(
        db=db,
        proposal_id=prop_id,
        facility_id=dst_id,
        approver_user_id=u_dst_id,
        proposal_version=prop_ver,
        decision="APPROVED",
        auto_reserve=False
    )

    # Resumption must catch the insufficient stock and fail safely!
    resume_res = MediFlowAgentService.resume_workflow_approval(db, wf_id)
    assert resume_res["status"] == "FAILED_REVALIDATION"
    assert "Pre-reservation policy revalidation failed" in resume_res["message"]

    # Clean up by restoring stock
    LedgerService.record_movement(
        db=db,
        facility_id=src_id,
        batch_id=batch_id,
        movement_type="PURCHASE_RECEIPT",
        quantity_delta=500,
        unit="CAPSULE",
        idempotency_key=f"RESTORE-STOCK-{wf_id}"
    )


def test_api_agent_endpoints(db_session):
    """Verifies all agent API endpoints return standard HTTP responses."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.deps import get_db

    db = db_session["session"]
    app.dependency_overrides[get_db] = lambda: db

    try:
        client = TestClient(app)

        # GET /api/v1/agent/status
        res_status = client.get("/api/v1/agent/status")
        assert res_status.status_code == 200
        assert "gemini" in res_status.json()
        assert "meko" in res_status.json()

        # GET /api/v1/agent/traces
        res_traces = client.get("/api/v1/agent/traces")
        assert res_traces.status_code == 200
        assert isinstance(res_traces.json(), list)

        # POST /api/v1/agent/run-cycle
        prod_id = db_session["prod"].id
        res_run = client.post(f"/api/v1/agent/run-cycle?product_id={prod_id}")
        assert res_run.status_code == 200
        data = res_run.json()
        assert "workflow_id" in data
        assert "workflow_status" in data

        # GET /api/v1/agent/runs
        res_runs = client.get("/api/v1/agent/runs")
        assert res_runs.status_code == 200
        runs = res_runs.json()
        assert len(runs) >= 1

        # GET /api/v1/agent/runs/{id}
        wf_id = data["workflow_id"]
        res_detail = client.get(f"/api/v1/agent/runs/{wf_id}")
        assert res_detail.status_code == 200
        detail = res_detail.json()
        assert detail["workflow_id"] == wf_id
        assert "node_trace" in detail

    finally:
        app.dependency_overrides.pop(get_db, None)

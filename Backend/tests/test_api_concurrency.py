import os
import pytest

# Override DATABASE_URL to SQLite BEFORE any app imports.
# Prevents these integration tests from hanging on unreachable YugabyteDB cloud.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_concurrency.db")

from app.core.database import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.schemas.domain import RiskAssessmentResponse
from app.services.seed_service import seed_database
from app.models.inventory import FacilityBatchInventory
from app.models.proposal import TransferProposal
from app.models.product import Product, Batch
from app.services.proposal_service import ProposalService
from app.api.routes.dashboard import get_dashboard_overview
from app.api.routes.facilities import list_facilities
from app.api.routes.risks import get_risks
from app.api.routes.proposals import list_redistribution_opportunities


@pytest.fixture(scope="module")
def db():
    """Use an in-process SQLite engine for integration tests (no network required)."""
    test_engine = create_engine(
        "sqlite:///./test_concurrency.db",
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestSession()
    seed_database(session, force_reset=False)  # Tables already created; just seed
    yield session
    session.close()
    Base.metadata.drop_all(bind=test_engine)


def test_api_health_and_dashboard(db):
    data = get_dashboard_overview(db=db)
    assert data["total_facilities"] == 4
    assert data["monitored_products"] == 16
    assert data["active_stockout_risks"] > 0
    assert data["system_mode"] == "SIMULATION"


def test_api_facilities_and_risks(db):
    facs = list_facilities(db=db)
    assert len(facs) == 4

    risks = get_risks(db=db)
    assert len(risks) > 0
    types = {r["risk_type"] for r in risks}
    assert "STOCKOUT_RISK" in types
    assert "EXPIRY_RISK" in types
    validated_risks = [RiskAssessmentResponse.model_validate(risk) for risk in risks]
    assert len(validated_risks) == len(risks)


def test_api_opportunities_and_deterministic_rejections(db):
    data = list_redistribution_opportunities(db=db)
    assert "accepted_opportunities" in data
    assert "rejected_candidates" in data
    assert len(data["accepted_opportunities"]) > 0
    assert len(data["rejected_candidates"]) > 0


def test_concurrency_competing_reservations(db):
    """
    Simulates two transfer proposals competing for the exact same batch.
    Available stock = 50 units.
    Proposal 1 requests 40 units.
    Proposal 2 requests 30 units.
    Only Proposal 1 should succeed; Proposal 2 must fail cleanly with FAILED_INSUFFICIENT_STOCK.
    """
    # Fetch real product and batch
    from app.models.product import Product, Batch
    prod = db.query(Product).first()
    batch = db.query(Batch).filter(Batch.product_id == prod.id).first()
    
    # Find facility with stock
    inv = db.query(FacilityBatchInventory).filter(FacilityBatchInventory.batch_id == batch.id).first()
    assert inv is not None
    source_fac_id = inv.facility_id
    batch_id = inv.batch_id
    
    # Set exact usable balance to 50
    inv.on_hand_quantity = 50
    inv.reserved_quantity = 0
    inv.quarantined_quantity = 0
    inv.damaged_quantity = 0
    db.commit()

    # Find another facility
    all_inv = db.query(FacilityBatchInventory).filter(FacilityBatchInventory.facility_id != source_fac_id).first()
    dest_fac_id = all_inv.facility_id

    # Create Proposal 1 (wants 40 units)
    prop1 = ProposalService.create_proposal(
        db=db,
        source_facility_id=source_fac_id,
        destination_facility_id=dest_fac_id,
        product_id=prod.id,
        proposed_quantity=40,
        batches=[{"batch_id": batch_id, "quantity": 40}],
        source_rationale={},
        destination_rationale={}
    )

    # Create Proposal 2 (wants 30 units)
    prop2 = ProposalService.create_proposal(
        db=db,
        source_facility_id=source_fac_id,
        destination_facility_id=dest_fac_id,
        product_id=prod.id,
        proposed_quantity=30,
        batches=[{"batch_id": batch_id, "quantity": 30}],
        source_rationale={},
        destination_rationale={}
    )

    # Attempt to reserve Proposal 1
    res1 = ProposalService.reserve_stock_and_issue_labels(db, prop1)
    assert res1["success"] is True
    assert res1["status"] == "RESERVED"

    # Attempt to reserve Proposal 2 (should FAIL because only 10 units remain, but 30 requested)
    res2 = ProposalService.reserve_stock_and_issue_labels(db, prop2)
    assert res2["success"] is False
    assert res2["status"] == "FAILED_INSUFFICIENT_STOCK"
    assert "Reservation failed" in res2["message"]

    # Re-check inventory state: exactly 40 units reserved, 10 units usable, NO over-allocation
    db.refresh(inv)
    assert inv.reserved_quantity == 40
    assert inv.usable_quantity == 10

import os
import pytest
from datetime import datetime, timezone, timedelta, date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_forecast_risk.db")

from app.core.database import Base
from app.models.organization import Organisation, Facility
from app.models.product import Product, Batch
from app.models.consumption import ConsumptionRecord, PurchaseOrder, PurchaseOrderLine
from app.services.forecast_service import ForecastService
from app.services.risk_service import RiskService
from app.services.inventory_service import InventoryService
from app.services.ledger_service import LedgerService


@pytest.fixture(scope="module")
def db_session():
    test_engine = create_engine(
        "sqlite:///./test_forecast_risk.db",
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSession()

    try:
        org = Organisation(name="Test Regional Health")
        session.add(org)
        session.flush()

        fac_a = Facility(organisation_id=org.id, name="City Central Hospital", facility_type="HOSPITAL")
        fac_b = Facility(organisation_id=org.id, name="Rural Community Health", facility_type="HOSPITAL")
        session.add_all([fac_a, fac_b])
        session.flush()

        prod_mero = Product(
            internal_code="MED-TST-001",
            name="Meropenem 1g Injection",
            generic_name="Meropenem",
            strength="1g",
            dosage_form="INJECTION",
            base_unit="VIAL",
            storage_requirements="ROOM_TEMPERATURE"
        )
        prod_insu = Product(
            internal_code="MED-TST-002",
            name="Insulin Regular 100IU",
            generic_name="Insulin",
            strength="100IU",
            dosage_form="VIAL",
            base_unit="VIAL",
            storage_requirements="COLD_CHAIN_2_8C"
        )
        session.add_all([prod_mero, prod_insu])
        session.flush()

        # Seed 30 days of consumption for prod_mero at fac_a
        now = datetime.now(timezone.utc)
        for i in range(30):
            c_date = now - timedelta(days=(30 - i))
            # Upward trending consumption: from 5 up to 15 vials/day
            qty = 5 + int(i * 0.35)
            session.add(ConsumptionRecord(
                facility_id=fac_a.id,
                product_id=prod_mero.id,
                quantity=qty,
                unit="VIAL",
                consumed_at=c_date,
                source_system="TEST_HIS"
            ))
        session.flush()

        yield session, {
            "org": org,
            "fac_a": fac_a,
            "fac_b": fac_b,
            "prod_mero": prod_mero,
            "prod_insu": prod_insu
        }
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_consumption_aggregation_daily_and_weekly(db_session):
    session, ctx = db_session
    fac_a = ctx["fac_a"]
    prod_mero = ctx["prod_mero"]

    # Daily aggregation
    daily_agg = ForecastService.aggregate_consumption(
        session, facility_id=fac_a.id, product_id=prod_mero.id, window_days=60, period="daily"
    )
    assert daily_agg["period"] == "daily"
    assert daily_agg["unit"] == "VIAL"
    assert daily_agg["total_quantity"] > 0
    assert daily_agg["active_days"] >= 30
    assert len(daily_agg["daily_series"]) >= 30
    assert daily_agg["has_zero_demand"] is False

    # Weekly aggregation
    weekly_agg = ForecastService.aggregate_consumption(
        session, facility_id=fac_a.id, product_id=prod_mero.id, window_days=60, period="weekly"
    )
    assert weekly_agg["period"] == "weekly"
    assert weekly_agg["total_quantity"] == daily_agg["total_quantity"]
    assert len(weekly_agg["values"]) > 0


def test_insufficient_history_and_zero_demand(db_session):
    session, ctx = db_session
    fac_b = ctx["fac_b"]
    prod_insu = ctx["prod_insu"]

    # Product with no consumption records at fac_b
    agg = ForecastService.aggregate_consumption(
        session, facility_id=fac_b.id, product_id=prod_insu.id, window_days=60
    )
    assert agg["total_quantity"] == 0
    assert agg["has_zero_demand"] is True
    assert agg["has_insufficient_history"] is True
    assert len(agg["warnings"]) > 0
    assert any("Insufficient data" in w or "Zero demand" in w for w in agg["warnings"])

    # Forecast calculation for zero-demand product returns 0 estimate with warnings
    fc = ForecastService.calculate_forecast(session, fac_b.id, prod_insu.id, horizon_days=30)
    assert fc["daily_average_demand"] == 0.0
    assert fc["projected_total_demand"] == 0.0
    assert fc["demand_7d"] == 0.0
    assert fc["demand_30d"] == 0.0
    assert fc["model_name"] == "WEIGHTED_MOVING_AVERAGE"
    assert len(fc["warnings"]) > 0


def test_weighted_moving_average_recency_weighting(db_session):
    session, ctx = db_session
    fac_a = ctx["fac_a"]
    prod_mero = ctx["prod_mero"]

    fc = ForecastService.calculate_forecast(session, fac_a.id, prod_mero.id, horizon_days=30)
    assert fc["daily_average_demand"] > 0.0
    assert fc["projected_total_demand"] > 0.0
    assert fc["demand_7d"] > 0.0
    assert fc["demand_30d"] > 0.0
    assert fc["demand_30d"] >= fc["demand_7d"]
    assert len(fc["daily_estimates"]) == 30
    assert fc["confidence_score"] > 0.0
    assert fc["model_name"] == "WEIGHTED_MOVING_AVERAGE"

    # Verify recency effect: because consumption increased over time (5 -> 15),
    # WMA daily should be higher than simple arithmetic mean of the whole range
    agg = ForecastService.aggregate_consumption(session, fac_a.id, prod_mero.id, window_days=30)
    non_zero_vals = [v for v in agg["values"] if v > 0]
    simple_mean = sum(non_zero_vals) / len(non_zero_vals)
    # WMA puts more weight on the recent higher days
    assert fc["daily_average_demand"] >= simple_mean * 0.95


def test_projected_stock_formula_and_trajectory():
    # usable_on_hand: 100
    # daily_demand: 5
    # horizon: 10 days
    # inbound order: 40 units arriving on Day 5
    # outbound commitments: 10 units
    # expected end stock = 100 - (5 * 10) + 40 - 10 = 80 units
    today = date.today()
    inbound = [{"delivery_date": (today + timedelta(days=5)).isoformat(), "quantity": 40}]

    proj = ForecastService.calculate_projected_stock(
        usable_stock=100,
        daily_demand=5.0,
        horizon_days=10,
        inbound_deliveries=inbound,
        existing_outbound_commitments=10,
        safety_stock=20,
        start_date=today
    )

    assert proj["projected_stock_end"] == 80
    assert proj["confirmed_inbound_horizon"] == 40
    assert len(proj["trajectory"]) == 10
    # Day 5 should reflect the inbound delivery
    day_5 = proj["trajectory"][4]
    assert day_5["inbound"] == 40
    assert day_5["is_stockout"] is False


def test_projected_stock_detects_stockout_day():
    # usable_stock: 15 units, daily demand: 5 units/day, no inbound
    # Should stockout on Day 3
    today = date.today()
    proj = ForecastService.calculate_projected_stock(
        usable_stock=15,
        daily_demand=5.0,
        horizon_days=10,
        inbound_deliveries=[],
        existing_outbound_commitments=0,
        safety_stock=10,
        start_date=today
    )
    assert proj["stockout_day"] == 3
    assert proj["projected_stock_end"] == 0
    assert proj["safety_stock_breach_day"] == 2


def test_days_of_cover_deterministic_calculation():
    # Normal cover
    assert RiskService.calculate_days_of_cover(usable_stock=100, daily_demand=10.0) == 10.0
    assert RiskService.calculate_days_of_cover(usable_stock=15, daily_demand=12.0) == 1.2

    # Zero demand edge cases
    assert RiskService.calculate_days_of_cover(usable_stock=50, daily_demand=0.0) == 999.0
    assert RiskService.calculate_days_of_cover(usable_stock=0, daily_demand=0.0) == 0.0


def test_stockout_risk_threshold_grading():
    # Critical: days_of_cover <= 4 days (replenishment lead time)
    r_crit = RiskService.evaluate_stockout_risk(usable_stock=15, daily_demand=12.0)
    assert r_crit["risk_level"] == "CRITICAL"
    assert r_crit["score"] == 95.0
    assert r_crit["days_of_cover"] == 1.2
    assert r_crit["projected_stockout_date"] is not None

    # High: days_of_cover <= 7 days (safety stock buffer)
    r_high = RiskService.evaluate_stockout_risk(usable_stock=50, daily_demand=10.0)
    assert r_high["risk_level"] == "HIGH"
    assert r_high["score"] == 75.0
    assert r_high["days_of_cover"] == 5.0

    # Medium: days_of_cover <= 14 days
    r_med = RiskService.evaluate_stockout_risk(usable_stock=100, daily_demand=10.0)
    assert r_med["risk_level"] == "MEDIUM"
    assert r_med["score"] == 45.0
    assert r_med["days_of_cover"] == 10.0

    # Safe: days_of_cover > 30 days
    r_safe = RiskService.evaluate_stockout_risk(usable_stock=400, daily_demand=10.0)
    assert r_safe["risk_level"] == "SAFE"
    assert r_safe["score"] == 0.0


def test_fefo_expiry_depletion_simulation():
    today = date.today()
    # Batch 1: 50 units, expires in 20 days
    # Batch 2: 100 units, expires in 40 days
    # Daily demand = 3 units/day
    # Demand in first 20 days = 60 units. Batch 1 (50 units) is fully absorbed -> Leftover = 0
    # Demand in first 40 days = 120 units. 50 from Batch 1, leaving 70 units of demand for Batch 2.
    # Batch 2 has 100 units -> 30 units leftover unconsumed!
    batches = [
        {
            "batch_id": "b1",
            "manufacturer_lot_number": "LOT-B1",
            "expiry_date": today + timedelta(days=20),
            "days_to_expiry": 20,
            "usable_quantity": 50,
            "quality_status": "RELEASED"
        },
        {
            "batch_id": "b2",
            "manufacturer_lot_number": "LOT-B2",
            "expiry_date": today + timedelta(days=40),
            "days_to_expiry": 40,
            "usable_quantity": 100,
            "quality_status": "RELEASED"
        }
    ]

    exp_risks = RiskService.simulate_fefo_expiry_depletion(batches, daily_demand=3.0, planning_horizon_days=90)
    assert len(exp_risks) == 1
    flagged = exp_risks[0]
    assert flagged["batch_id"] == "b2"
    assert flagged["lot_number"] == "LOT-B2"
    assert flagged["unconsumed_quantity"] == 30
    assert flagged["risk_level"] == "HIGH"  # expires in 40 days (<= 60 days)


def test_already_expired_and_blocked_batches_handling():
    today = date.today()
    batches = [
        {
            "batch_id": "b_exp",
            "manufacturer_lot_number": "LOT-EXPIRED",
            "expiry_date": today - timedelta(days=5),
            "days_to_expiry": -5,
            "usable_quantity": 25,
            "quality_status": "RELEASED"
        },
        {
            "batch_id": "b_quar",
            "manufacturer_lot_number": "LOT-QUARANTINE",
            "expiry_date": today + timedelta(days=60),
            "days_to_expiry": 60,
            "usable_quantity": 40,
            "quality_status": "QUARANTINED"
        }
    ]

    exp_risks = RiskService.simulate_fefo_expiry_depletion(batches, daily_demand=5.0)
    # Already expired batch must be flagged CRITICAL
    assert any(r["batch_id"] == "b_exp" and r["risk_level"] == "CRITICAL" and r["is_already_expired"] for r in exp_risks)
    # Quarantined batch must be excluded from FEFO candidate redistribution
    assert not any(r["batch_id"] == "b_quar" for r in exp_risks)


def test_candidate_surplus_and_destination_need():
    # Source surplus:
    # Usable stock = 450 units, daily demand = 1.0, horizon = 30 days, safety stock = 7 days
    # Protected = (30 + 7) * 1.0 = 37 units
    # Surplus = 450 - 37 = 413 units
    surplus = RiskService.calculate_candidate_surplus(
        usable_stock=450,
        daily_demand=1.0,
        safety_stock_days=7,
        horizon_days=30
    )
    assert surplus == 413

    # Destination need:
    # Target stock = 12.0 * 37 = 444 units
    # Current stock = 15 units, confirmed inbound = 200 units, horizon demand = 12 * 30 = 360 units
    # Projected stock after inbound = 15 + 200 - 360 = -145
    # Unmet need = max(0, 444 - (-145)) = 589 units
    need = RiskService.calculate_destination_unmet_need(
        target_stock_days=37,
        daily_demand=12.0,
        current_usable_stock=15,
        confirmed_inbound=200,
        horizon_days=30
    )
    assert need == 589

    # Transfer quantity allocation
    alloc = RiskService.calculate_eligible_transfer_quantity(
        candidate_surplus=surplus,
        destination_unmet_need=need,
        batch_eligible_quantity=100,
        transfer_policy_limit=150
    )
    assert alloc == 100  # Constrained by batch eligible quantity


def test_api_forecast_and_risk_endpoints(db_session):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.deps import get_db

    session, ctx = db_session
    fac_a = ctx["fac_a"]
    prod_mero = ctx["prod_mero"]

    # Override get_db to use test fixture session
    app.dependency_overrides[get_db] = lambda: session
    try:
        client = TestClient(app)

        # 1. GET /api/v1/forecasts with facility & product
        r1 = client.get(f"/api/v1/forecasts?facility_id={fac_a.id}&product_id={prod_mero.id}&horizon_days=30")
        assert r1.status_code == 200
        fc_data = r1.json()
        assert fc_data["facility_id"] == fac_a.id
        assert fc_data["product_id"] == prod_mero.id
        assert fc_data["model_name"] == "WEIGHTED_MOVING_AVERAGE"
        assert "demand_7d" in fc_data
        assert "demand_30d" in fc_data
        assert "daily_estimates" in fc_data

        # 2. POST /api/v1/forecasts/run
        r2 = client.post("/api/v1/forecasts/run", json={
            "facility_id": fac_a.id,
            "product_id": prod_mero.id,
            "horizon_days": 30
        })
        assert r2.status_code == 200
        run_data = r2.json()
        assert run_data["total_runs"] >= 1

        # 3. GET /api/v1/risks
        r3 = client.get("/api/v1/risks")
        assert r3.status_code == 200
        risks_list = r3.json()
        assert isinstance(risks_list, list)

        # 4. GET /api/v1/risks/summary
        r4 = client.get("/api/v1/risks/summary")
        assert r4.status_code == 200
        sum_data = r4.json()
        assert "total_risks" in sum_data
        assert "stockout_risks" in sum_data
        assert "expiry_risks" in sum_data

        # 5. GET /api/v1/dashboard/risks-summary
        r5 = client.get("/api/v1/dashboard/risks-summary")
        assert r5.status_code == 200
        dash_sum = r5.json()
        assert "stockout_risks" in dash_sum

        # 6. GET /api/v1/risks/{risk_id}
        if risks_list:
            sample_id = risks_list[0]["id"]
            r6 = client.get(f"/api/v1/risks/{sample_id}")
            assert r6.status_code == 200
            assert r6.json()["id"] == sample_id
    finally:
        app.dependency_overrides.clear()

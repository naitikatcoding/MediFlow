from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models
from app.core.database import Base
from app.models.inventory import FacilityBatchInventory
from app.models.organization import Facility, Organisation
from app.models.product import Batch, Product
from app.schemas.chat import ChatResponse
from app.services import chat_service


@pytest.fixture
def chat_db():
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    test_session = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    db = test_session()

    organisation = Organisation(name="Chat Test Network")
    db.add(organisation)
    db.flush()
    facility = Facility(
        organisation_id=organisation.id,
        name="North Test Hospital",
        facility_type="HOSPITAL",
        storage_capabilities={"cold_chain": True},
    )
    product = Product(
        internal_code="MED-CHAT-01",
        name="Ceftriaxone 1g Injection",
        generic_name="Ceftriaxone",
        strength="1g",
        dosage_form="INJECTION",
        base_unit="VIAL",
    )
    paracetamol = Product(
        internal_code="MED-CHAT-02",
        name="Paracetamol 1g IV Infusion",
        generic_name="Paracetamol",
        strength="1g",
        dosage_form="INFUSION",
        base_unit="BOTTLE",
    )
    db.add_all([facility, product, paracetamol])
    db.flush()
    batch = Batch(
        product_id=product.id,
        manufacturer_lot_number="CHAT-LOT-1",
        expiry_date=date.today() + timedelta(days=120),
        manufacturer="Test Pharma",
        quality_status="RELEASED",
    )
    db.add(batch)
    db.flush()
    db.add(
        FacilityBatchInventory(
            facility_id=facility.id,
            batch_id=batch.id,
            on_hand_quantity=60,
            reserved_quantity=8,
            quarantined_quantity=5,
            damaged_quantity=5,
            unit="VIAL",
        )
    )
    expired_batch = Batch(
        product_id=paracetamol.id,
        manufacturer_lot_number="CHAT-LOT-EXPIRED",
        expiry_date=date.today() - timedelta(days=30),
        manufacturer="Test Pharma",
        quality_status="RELEASED",
    )
    db.add(expired_batch)
    db.flush()
    db.add(
        FacilityBatchInventory(
            facility_id=facility.id,
            batch_id=expired_batch.id,
            on_hand_quantity=14,
            reserved_quantity=0,
            quarantined_quantity=0,
            damaged_quantity=0,
            unit="BOTTLE",
        )
    )
    upcoming_batch = Batch(
        product_id=paracetamol.id,
        manufacturer_lot_number="CHAT-LOT-UPCOMING",
        expiry_date=date.today() + timedelta(days=12),
        manufacturer="Test Pharma",
        quality_status="RELEASED",
    )
    db.add(upcoming_batch)
    db.flush()
    db.add(
        FacilityBatchInventory(
            facility_id=facility.id,
            batch_id=upcoming_batch.id,
            on_hand_quantity=6,
            reserved_quantity=1,
            quarantined_quantity=0,
            damaged_quantity=0,
            unit="BOTTLE",
        )
    )
    db.commit()
    try:
        yield db, facility
    finally:
        db.close()
        test_engine.dispose()


def add_second_facility_inventory(db, facility):
    second_facility = Facility(
        organisation_id=facility.organisation_id,
        name="South Test Hospital",
        facility_type="HOSPITAL",
        storage_capabilities={"cold_chain": True},
    )
    batch = db.query(Batch).filter(Batch.manufacturer_lot_number == "CHAT-LOT-1").one()
    db.add(second_facility)
    db.flush()
    db.add(
        FacilityBatchInventory(
            facility_id=second_facility.id,
            batch_id=batch.id,
            on_hand_quantity=25,
            reserved_quantity=0,
            quarantined_quantity=0,
            damaged_quantity=0,
            unit="VIAL",
        )
    )
    db.commit()
    return second_facility


def test_chat_answers_stock_from_live_operational_inventory(monkeypatch, chat_db):
    db, facility = chat_db
    monkeypatch.setattr(
        chat_service,
        "_retrieve_context",
        lambda *_args, **_kwargs: pytest.fail("live stock answers should not use RAG fallback"),
    )

    response = chat_service.answer_chat(
        db,
        "How much Ceftriaxone stock is left?",
        facility_id=facility.id,
    )

    assert response["retrieval_provider"] == "operational_database"
    assert response["answer_provider"] == "grounded_fallback"
    assert response["answer"] == (
        "Ceftriaxone 1g Injection at North Test Hospital: "
        "60 VIAL on hand; 42 VIAL eligible for use."
    )
    assert any(source["source"] == "Operational database" for source in response["sources"])


def test_expired_stock_answer_is_concise_and_uses_only_current_medicine(monkeypatch, chat_db):
    db, facility = chat_db
    monkeypatch.setattr(chat_service.meko_adapter, "retrieve_context", lambda **kwargs: [])
    monkeypatch.setattr(chat_service.database, "is_yugabyte_active", lambda: False)
    monkeypatch.setattr(chat_service.database, "get_local_knowledge_engine", db.get_bind)
    monkeypatch.setattr(chat_service.settings, "GEMINI_API_KEY", None)

    response = chat_service.answer_chat(
        db,
        "How much stock of Paracetamol is expired?",
        facility_id=facility.id,
        history=[
            {"role": "user", "content": "How much Ceftriaxone stock is left?"},
            {"role": "assistant", "content": "Ceftriaxone stock is 60 VIAL."},
        ],
    )

    assert response["answer"] == (
        "Paracetamol 1g IV Infusion at North Test Hospital: 14 BOTTLE expired."
    )
    assert all("Ceftriaxone" not in suggestion for suggestion in response["suggestions"])
    assert len(response["suggestions"]) == 3


def test_expired_stock_question_with_no_matching_product_asks_for_medicine(monkeypatch, chat_db):
    db, facility = chat_db
    monkeypatch.setattr(chat_service.meko_adapter, "retrieve_context", lambda **kwargs: [])
    monkeypatch.setattr(chat_service.database, "is_yugabyte_active", lambda: False)
    monkeypatch.setattr(chat_service.database, "get_local_knowledge_engine", db.get_bind)
    monkeypatch.setattr(chat_service.settings, "GEMINI_API_KEY", None)

    response = chat_service.answer_chat(
        db,
        "How much stock is expired?",
        facility_id=facility.id,
    )

    assert response["answer"] == "Which medicine should I check for expired stock?"


def test_eligible_stock_question_does_not_count_expired_inventory(monkeypatch, chat_db):
    db, facility = chat_db
    monkeypatch.setattr(chat_service.meko_adapter, "retrieve_context", lambda **kwargs: [])
    monkeypatch.setattr(chat_service.database, "is_yugabyte_active", lambda: False)
    monkeypatch.setattr(chat_service.database, "get_local_knowledge_engine", db.get_bind)
    monkeypatch.setattr(chat_service.settings, "GEMINI_API_KEY", None)

    response = chat_service.answer_chat(
        db,
        "How much eligible Paracetamol stock remains?",
        facility_id=facility.id,
    )

    assert response["answer"] == (
        "Paracetamol 1g IV Infusion at North Test Hospital: "
        "5 BOTTLE eligible, non-expired stock."
    )


def test_closest_expiry_question_uses_live_batches_and_skips_rag(monkeypatch, chat_db):
    db, facility = chat_db
    monkeypatch.setattr(
        chat_service,
        "_retrieve_context",
        lambda *_args, **_kwargs: pytest.fail("live expiry query should not use RAG fallback"),
    )

    response = chat_service.answer_chat(
        db,
        "Which batches are closest to expiry?",
        facility_id=facility.id,
    )

    lines = response["answer"].splitlines()
    assert lines[0].startswith("CHAT-LOT-UPCOMING — Paracetamol 1g IV Infusion")
    assert "6 BOTTLE, expires" in lines[0]
    assert lines[1].startswith("CHAT-LOT-1 — Ceftriaxone 1g Injection")
    assert "CHAT-LOT-EXPIRED" not in response["answer"]
    assert response["retrieval_provider"] == "operational_database"
    assert response["suggestions"] == [
        "Which facility has the nearest-expiring batch?",
        "How much stock is in the nearest-expiring batch?",
        "Show batches expiring within 30 days.",
    ]
    assert all(source["source"] == "Operational database" for source in response["sources"])
    assert ChatResponse.model_validate(response).retrieval_provider == "operational_database"


def test_chat_question_can_override_selected_facility(monkeypatch, chat_db):
    db, selected_facility = chat_db
    add_second_facility_inventory(db, selected_facility)
    monkeypatch.setattr(chat_service.meko_adapter, "retrieve_context", lambda **kwargs: [])
    monkeypatch.setattr(chat_service.database, "is_yugabyte_active", lambda: False)
    monkeypatch.setattr(chat_service.database, "get_local_knowledge_engine", db.get_bind)
    monkeypatch.setattr(chat_service.settings, "GEMINI_API_KEY", None)

    response = chat_service.answer_chat(
        db,
        "How much Ceftriaxone stock is at South Test Hospital?",
        facility_id=selected_facility.id,
    )

    assert response["answer"] == (
        "Ceftriaxone 1g Injection at South Test Hospital: "
        "25 VIAL on hand; 25 VIAL eligible for use."
    )


def test_chat_all_facilities_question_ignores_selected_facility(monkeypatch, chat_db):
    db, selected_facility = chat_db
    add_second_facility_inventory(db, selected_facility)
    monkeypatch.setattr(chat_service.meko_adapter, "retrieve_context", lambda **kwargs: [])
    monkeypatch.setattr(chat_service.database, "is_yugabyte_active", lambda: False)
    monkeypatch.setattr(chat_service.database, "get_local_knowledge_engine", db.get_bind)
    monkeypatch.setattr(chat_service.settings, "GEMINI_API_KEY", None)

    response = chat_service.answer_chat(
        db,
        "How much Ceftriaxone stock is available across all facilities?",
        facility_id=selected_facility.id,
    )

    assert "North Test Hospital" in response["answer"]
    assert "South Test Hospital" in response["answer"]
    assert "60 VIAL on hand" in response["answer"]
    assert "25 VIAL on hand" in response["answer"]


def test_chat_prioritizes_live_meko_context_over_pgvector(monkeypatch, chat_db):
    db, facility = chat_db
    monkeypatch.setattr(
        type(chat_service.meko_adapter),
        "is_available",
        property(lambda _: True),
    )
    monkeypatch.setattr(
        chat_service.meko_adapter,
        "retrieve_context",
        lambda **kwargs: [
            {
                "ref_id": "meko-1",
                "summary": "The network requires dual approval for transfers.",
                "provenance": "LIVE_MEKO",
            }
        ],
    )
    monkeypatch.setattr(chat_service.database, "is_yugabyte_active", lambda: True)
    monkeypatch.setattr(
        chat_service,
        "_retrieve_yugabyte_chunks",
        lambda *_args, **_kwargs: pytest.fail("pgvector should not run when MEKO has context"),
    )
    monkeypatch.setattr(chat_service.settings, "GEMINI_API_KEY", None)

    response = chat_service.answer_chat(
        db,
        "How are transfers approved?",
        facility_id=facility.id,
    )

    assert response["retrieval_provider"] == "meko"
    assert any(source["source"] == "MEKO shared memory" for source in response["sources"])


def test_chat_uses_yugabyte_pgvector_when_meko_has_no_context(monkeypatch, chat_db):
    db, facility = chat_db
    monkeypatch.setattr(chat_service.meko_adapter, "retrieve_context", lambda **kwargs: [])
    monkeypatch.setattr(chat_service.database, "is_yugabyte_active", lambda: True)
    monkeypatch.setattr(
        chat_service,
        "_retrieve_yugabyte_chunks",
        lambda *_args, **_kwargs: [
            {
                "id": "expiry-fefo",
                "title": "Expiry and FEFO handling",
                "content": "MediFlow orders batches by expiry date.",
            }
        ],
    )
    monkeypatch.setattr(chat_service.settings, "GEMINI_API_KEY", None)

    response = chat_service.answer_chat(
        db,
        "Explain expiry and FEFO.",
        facility_id=facility.id,
    )

    assert response["retrieval_provider"] == "yugabyte_pgvector"
    assert response["sources"][0]["source"] == "YugabyteDB pgvector"


def test_chat_request_rejects_oversized_question():
    from app.schemas.chat import ChatRequest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ChatRequest(question="x" * 2001)

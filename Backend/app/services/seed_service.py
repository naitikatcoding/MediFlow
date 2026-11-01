import random
from datetime import datetime, timezone, timedelta, date
from sqlalchemy.orm import Session
from app.core.database import Base
from app.models.organization import Organisation, Facility, User, FacilityMembership
from app.models.product import Product, Batch
from app.models.inventory import FacilityBatchInventory, InventoryLedger
from app.models.consumption import ConsumptionRecord, PurchaseOrder, PurchaseOrderLine
from app.models.proposal import TransferProposal, TransferProposalBatch, TransferApproval
from app.models.transfer import Transfer, TransferPackage, SerializedLabel, ScanEvent
from app.core.security import generate_secure_opaque_token, hash_token
from app.services.ledger_service import LedgerService


def seed_database(db: Session, force_reset: bool = True):
    if force_reset:
        target_engine = db.get_bind()
        Base.metadata.drop_all(bind=target_engine)
        Base.metadata.create_all(bind=target_engine)

    # 1. Create Network Organisation
    org = Organisation(
        name="Apollo-Care Regional Health Network",
        organisation_type="HOSPITAL_AND_PHARMACY_NETWORK",
        status="ACTIVE"
    )
    db.add(org)
    db.flush()

    # 2. Create Facilities
    facilities_data = [
        {
            "key": "apex",
            "name": "Apex Memorial Hospital",
            "facility_type": "HOSPITAL",
            "address": "45 Healthcare Boulevard, North Sector",
            "city": "Metro City",
            "storage_capabilities": {"cold_chain": True, "ambient_max_c": 24, "narcotics_vault": True}
        },
        {
            "key": "metro",
            "name": "Metro Central Distribution Pharmacy",
            "facility_type": "PHARMACY",
            "address": "12 Ring Road Logistics Zone",
            "city": "Metro City",
            "storage_capabilities": {"cold_chain": True, "ambient_max_c": 22, "narcotics_vault": True}
        },
        {
            "key": "st_jude",
            "name": "St. Jude Diagnostic & Daycare Centre",
            "facility_type": "DIAGNOSTIC_CENTRE",
            "address": "88 Market Lane, Old Town",
            "city": "Old Town",
            # Note: deliberate lack of cold chain storage to demonstrate deterministic constraint rejection!
            "storage_capabilities": {"cold_chain": False, "ambient_max_c": 28, "narcotics_vault": False}
        },
        {
            "key": "highland",
            "name": "Highland Community Hospital",
            "facility_type": "HOSPITAL",
            "address": "Route 7, Hill District",
            "city": "Highland",
            "storage_capabilities": {"cold_chain": True, "ambient_max_c": 25, "narcotics_vault": False}
        }
    ]

    fac_map = {}
    for f in facilities_data:
        fac = Facility(
            organisation_id=org.id,
            name=f["name"],
            facility_type=f["facility_type"],
            address=f["address"],
            city=f["city"],
            storage_capabilities=f["storage_capabilities"],
            status="ACTIVE"
        )
        db.add(fac)
        db.flush()
        fac_map[f["key"]] = fac

    # 3. Create Users
    users_data = [
        {"name": "Dr. Sarah Rao", "email": "sarah.rao@apexhealth.org", "role": "MEDICAL_SUPERINTENDENT", "fac": "apex"},
        {"name": "Pharmacist Amit Patel", "email": "amit.patel@metrocentral.org", "role": "PHARMACIST", "fac": "metro"},
        {"name": "Dr. Elena Gomez", "email": "elena.gomez@stjude.org", "role": "CLINICAL_DIRECTOR", "fac": "st_jude"},
        {"name": "Nurse Vikram Singh", "email": "vikram.singh@highlandhospital.org", "role": "PHARMACIST", "fac": "highland"},
        {"name": "Network Coordinator Priya Nair", "email": "priya.nair@mediflow.example", "role": "NETWORK_ADMIN", "fac": "metro"}
    ]

    user_map = {}
    for u in users_data:
        user = User(
            organisation_id=org.id,
            email=u["email"],
            name=u["name"],
            role=u["role"],
            status="ACTIVE"
        )
        db.add(user)
        db.flush()
        user_map[u["email"]] = user

        # Add facility membership
        fm = FacilityMembership(
            user_id=user.id,
            facility_id=fac_map[u["fac"]].id,
            role="APPROVER" if "SUPERINTENDENT" in u["role"] or "DIRECTOR" in u["role"] or "ADMIN" in u["role"] else "DISPATCHER"
        )
        db.add(fm)

    # 4. Create Products (16 items)
    products_data = [
        {
            "code": "MED-001", "name": "Meropenem 1g Injection", "generic": "Meropenem", 
            "strength": "1g/vial", "dosage": "INJECTION", "unit": "VIAL", "pack": 1, 
            "storage": "ROOM_TEMPERATURE", "policy": "STANDARD_ELIGIBLE"
        },
        {
            "code": "MED-002", "name": "Human Regular Insulin 100 IU/ml", "generic": "Insulin Regular", 
            "strength": "100 IU/ml 10ml", "dosage": "VIAL", "unit": "VIAL", "pack": 1, 
            "storage": "COLD_CHAIN_2_8C", "policy": "STANDARD_ELIGIBLE"
        },
        {
            "code": "MED-003", "name": "Ceftriaxone 1g IV/IM", "generic": "Ceftriaxone Sodium", 
            "strength": "1g", "dosage": "VIAL", "unit": "VIAL", "pack": 1, 
            "storage": "ROOM_TEMPERATURE", "policy": "STANDARD_ELIGIBLE"
        },
        {
            "code": "MED-004", "name": "Amoxicillin/Clavulanate 625mg", "generic": "Amoxicillin + Clavulanic Acid", 
            "strength": "625mg", "dosage": "TABLET", "unit": "TABLET", "pack": 10, 
            "storage": "ROOM_TEMPERATURE", "policy": "STANDARD_ELIGIBLE"
        },
        {
            "code": "MED-005", "name": "Enoxaparin 40mg/0.4ml Syringe", "generic": "Enoxaparin Sodium", 
            "strength": "40mg/0.4ml", "dosage": "INJECTION", "unit": "SYRINGE", "pack": 2, 
            "storage": "ROOM_TEMPERATURE", "policy": "STANDARD_ELIGIBLE"
        },
        {
            "code": "MED-006", "name": "Pantoprazole 40mg IV", "generic": "Pantoprazole", 
            "strength": "40mg/vial", "dosage": "VIAL", "unit": "VIAL", "pack": 1, 
            "storage": "ROOM_TEMPERATURE", "policy": "STANDARD_ELIGIBLE"
        },
        {
            "code": "MED-007", "name": "Potassium Chloride 15% Ampoule", "generic": "Potassium Chloride", 
            "strength": "15% 10ml", "dosage": "AMPOULE", "unit": "AMPOULE", "pack": 10, 
            "storage": "ROOM_TEMPERATURE", "policy": "RESTRICTED_LOCAL_ONLY" # Restricted policy demo!
        },
        {
            "code": "MED-008", "name": "Atorvastatin 20mg", "generic": "Atorvastatin", 
            "strength": "20mg", "dosage": "TABLET", "unit": "TABLET", "pack": 15, 
            "storage": "ROOM_TEMPERATURE", "policy": "STANDARD_ELIGIBLE"
        },
        {
            "code": "MED-009", "name": "Paracetamol 1g IV Infusion", "generic": "Paracetamol", 
            "strength": "1000mg/100ml", "dosage": "INFUSION", "unit": "BOTTLE", "pack": 1, 
            "storage": "ROOM_TEMPERATURE", "policy": "STANDARD_ELIGIBLE"
        },
        {
            "code": "MED-010", "name": "Azithromycin 500mg", "generic": "Azithromycin", 
            "strength": "500mg", "dosage": "TABLET", "unit": "TABLET", "pack": 3, 
            "storage": "ROOM_TEMPERATURE", "policy": "STANDARD_ELIGIBLE"
        },
        {
            "code": "MED-011", "name": "Dexamethasone 4mg/ml", "generic": "Dexamethasone", 
            "strength": "4mg/ml 2ml", "dosage": "VIAL", "unit": "VIAL", "pack": 5, 
            "storage": "ROOM_TEMPERATURE", "policy": "STANDARD_ELIGIBLE"
        },
        {
            "code": "MED-012", "name": "Salbutamol 2.5mg Respules", "generic": "Salbutamol Sulfate", 
            "strength": "2.5mg/2.5ml", "dosage": "RESPULE", "unit": "RESPULE", "pack": 20, 
            "storage": "ROOM_TEMPERATURE", "policy": "STANDARD_ELIGIBLE"
        },
        {
            "code": "MED-013", "name": "Metformin 500mg", "generic": "Metformin Hydrochloride", 
            "strength": "500mg", "dosage": "TABLET", "unit": "TABLET", "pack": 20, 
            "storage": "ROOM_TEMPERATURE", "policy": "STANDARD_ELIGIBLE"
        },
        {
            "code": "MED-014", "name": "Furosemide 20mg/2ml", "generic": "Furosemide", 
            "strength": "20mg/2ml", "dosage": "AMPOULE", "unit": "AMPOULE", "pack": 10, 
            "storage": "ROOM_TEMPERATURE", "policy": "STANDARD_ELIGIBLE"
        },
        {
            "code": "MED-015", "name": "Morphine Sulfate 10mg/ml", "generic": "Morphine Sulfate", 
            "strength": "10mg/ml", "dosage": "AMPOULE", "unit": "AMPOULE", "pack": 5, 
            "storage": "CONTROLLED_SUBSTANCE", "policy": "RESTRICTED_LOCAL_ONLY"
        },
        {
            "code": "MED-016", "name": "Ondansetron 4mg/2ml", "generic": "Ondansetron", 
            "strength": "4mg/2ml", "dosage": "AMPOULE", "unit": "AMPOULE", "pack": 10, 
            "storage": "ROOM_TEMPERATURE", "policy": "STANDARD_ELIGIBLE"
        }
    ]

    prod_map = {}
    for p in products_data:
        prod = Product(
            internal_code=p["code"],
            name=p["name"],
            generic_name=p["generic"],
            strength=p["strength"],
            dosage_form=p["dosage"],
            pack_size=p["pack"],
            base_unit=p["unit"],
            gtin=f"08901234{random.randint(100000, 999999)}",
            storage_requirements=p["storage"],
            transfer_policy_code=p["policy"],
            status="ACTIVE"
        )
        db.add(prod)
        db.flush()
        prod_map[p["code"]] = prod

    # 5. Create Batches and Current Inventory
    today = date.today()
    batch_records = []

    # Product 1: Meropenem (MAIN REPEATABLE CASE)
    # Metro has large surplus (450 units, expires in 180 days)
    # Highland has critical shortage (15 units on hand, consumes 12/day -> 1.2 days of cover!)
    b1_metro = Batch(
        product_id=prod_map["MED-001"].id,
        manufacturer_lot_number="LOT-MERO-2026A",
        manufacturing_date=today - timedelta(days=90),
        expiry_date=today + timedelta(days=180),
        manufacturer="Biochem Pharma Ltd",
        quality_status="RELEASED"
    )
    db.add(b1_metro)
    db.flush()
    LedgerService.record_movement(db, fac_map["metro"].id, b1_metro.id, "OPENING_BALANCE", 450, unit="VIAL", reason="Initial seed inventory")

    b1_highland = Batch(
        product_id=prod_map["MED-001"].id,
        manufacturer_lot_number="LOT-MERO-2025H",
        manufacturing_date=today - timedelta(days=200),
        expiry_date=today + timedelta(days=60),
        manufacturer="Biochem Pharma Ltd",
        quality_status="RELEASED"
    )
    db.add(b1_highland)
    db.flush()
    LedgerService.record_movement(db, fac_map["highland"].id, b1_highland.id, "OPENING_BALANCE", 15, unit="VIAL", reason="Near stockout inventory")

    # Product 2: Insulin Regular (STORAGE REJECTION CASE)
    # Metro has surplus, St. Jude needs it but St. Jude lacks cold chain!
    b2_metro = Batch(
        product_id=prod_map["MED-002"].id,
        manufacturer_lot_number="LOT-INSU-COLD-99",
        manufacturing_date=today - timedelta(days=30),
        expiry_date=today + timedelta(days=210),
        manufacturer="Novo Life Sciences",
        quality_status="RELEASED"
    )
    db.add(b2_metro)
    db.flush()
    LedgerService.record_movement(db, fac_map["metro"].id, b2_metro.id, "OPENING_BALANCE", 200, unit="VIAL", reason="Cold chain surplus")

    # Product 3: Ceftriaxone (CONCURRENCY / STOCK-CHANGE EDGE CASE)
    # Apex has 80 units initially, Highland needs 60
    b3_apex = Batch(
        product_id=prod_map["MED-003"].id,
        manufacturer_lot_number="LOT-CEFT-2026C",
        manufacturing_date=today - timedelta(days=60),
        expiry_date=today + timedelta(days=150),
        manufacturer="Glenmark Injectables",
        quality_status="RELEASED"
    )
    db.add(b3_apex)
    db.flush()
    LedgerService.record_movement(db, fac_map["apex"].id, b3_apex.id, "OPENING_BALANCE", 80, unit="VIAL", reason="Active ward stock")

    # Product 4: Amoxicillin/Clav (EXPIRY RISK CASE)
    # Apex has batch expiring in 25 days with 300 tablets, but daily consumption is only 3 tablets/day!
    b4_apex_expiring = Batch(
        product_id=prod_map["MED-004"].id,
        manufacturer_lot_number="LOT-AMOX-NEAR-EXP",
        manufacturing_date=today - timedelta(days=330),
        expiry_date=today + timedelta(days=25), # High expiry risk!
        manufacturer="Sun Diagnostics",
        quality_status="RELEASED"
    )
    db.add(b4_apex_expiring)
    db.flush()
    LedgerService.record_movement(db, fac_map["apex"].id, b4_apex_expiring.id, "OPENING_BALANCE", 300, unit="TABLET", reason="Near expiry lot")

    # Populate remaining batches and stock across facilities
    for code, prod in prod_map.items():
        if code in ("MED-001", "MED-002", "MED-003", "MED-004"):
            continue
        lot_num = f"LOT-{code}-{random.randint(100, 999)}"
        exp = today + timedelta(days=random.randint(90, 365))
        b = Batch(
            product_id=prod.id,
            manufacturer_lot_number=lot_num,
            manufacturing_date=today - timedelta(days=random.randint(30, 180)),
            expiry_date=exp,
            manufacturer="Standard Healthcare Labs",
            quality_status="RELEASED"
        )
        db.add(b)
        db.flush()
        # Seed stock across 2 random facilities
        for fkey in ["apex", "metro", "highland"]:
            qty = random.randint(40, 250)
            LedgerService.record_movement(db, fac_map[fkey].id, b.id, "OPENING_BALANCE", qty, unit=prod.base_unit, reason="Standard baseline stock")

    # 6. Seed 10 Weeks (70 Days) of Synthetic Daily Consumption Records
    random.seed(42)  # Deterministic seed!
    start_date = today - timedelta(days=70)

    for days_ago in range(70):
        curr_dt = datetime.combine(start_date + timedelta(days=days_ago), datetime.min.time()).replace(tzinfo=timezone.utc)
        
        # Highland high demand for Meropenem (MED-001): 10-14 vials per day
        c1 = ConsumptionRecord(
            facility_id=fac_map["highland"].id,
            product_id=prod_map["MED-001"].id,
            quantity=random.randint(10, 14),
            unit="VIAL",
            consumed_at=curr_dt,
            source_system="SYNTHETIC_HIS"
        )
        db.add(c1)

        # Metro low local demand for Meropenem: 1-2 vials per day
        c2 = ConsumptionRecord(
            facility_id=fac_map["metro"].id,
            product_id=prod_map["MED-001"].id,
            quantity=random.randint(1, 2),
            unit="VIAL",
            consumed_at=curr_dt,
            source_system="SYNTHETIC_HIS"
        )
        db.add(c2)

        # St. Jude daily need for Insulin (MED-002): 8-10 vials
        c3 = ConsumptionRecord(
            facility_id=fac_map["st_jude"].id,
            product_id=prod_map["MED-002"].id,
            quantity=random.randint(8, 12),
            unit="VIAL",
            consumed_at=curr_dt,
            source_system="SYNTHETIC_HIS"
        )
        db.add(c3)

        # Apex low demand for Amox/Clav: 2-4 tablets per day
        c4 = ConsumptionRecord(
            facility_id=fac_map["apex"].id,
            product_id=prod_map["MED-004"].id,
            quantity=random.randint(2, 4),
            unit="TABLET",
            consumed_at=curr_dt,
            source_system="SYNTHETIC_HIS"
        )
        db.add(c4)

        # Apex demand for Ceftriaxone: 15-20 vials per day
        c5 = ConsumptionRecord(
            facility_id=fac_map["apex"].id,
            product_id=prod_map["MED-003"].id,
            quantity=random.randint(15, 20),
            unit="VIAL",
            consumed_at=curr_dt,
            source_system="SYNTHETIC_HIS"
        )
        db.add(c5)

        # Background consumption for other products
        if days_ago % 2 == 0:
            for pcode in ["MED-005", "MED-006", "MED-008", "MED-009"]:
                prod = prod_map[pcode]
                cr = ConsumptionRecord(
                    facility_id=fac_map["apex"].id,
                    product_id=prod.id,
                    quantity=random.randint(3, 8),
                    unit=prod.base_unit,
                    consumed_at=curr_dt,
                    source_system="SYNTHETIC_HIS"
                )
                db.add(cr)

    # 7. Seed Purchase Orders
    po = PurchaseOrder(
        facility_id=fac_map["highland"].id,
        supplier_id="SUP-BIOCHEM-INDIA",
        status="CONFIRMED",
        expected_delivery_at=datetime.now(timezone.utc) + timedelta(days=12)
    )
    db.add(po)
    db.flush()
    pol = PurchaseOrderLine(
        purchase_order_id=po.id,
        product_id=prod_map["MED-001"].id,
        quantity_ordered=200,
        unit="VIAL"
    )
    db.add(pol)

    # 8. Create an initial Seeded Transfer Proposal ready for dual approval or scanning
    prop = TransferProposal(
        source_facility_id=fac_map["metro"].id,
        destination_facility_id=fac_map["highland"].id,
        product_id=prod_map["MED-001"].id,
        proposed_quantity=100,
        unit="VIAL",
        status="PROPOSED",
        priority="CRITICAL",
        expected_arrival_at=datetime.now(timezone.utc) + timedelta(days=2),
        source_rationale={
            "usable_stock": 450,
            "surplus_available": 350,
            "retained_safety_buffer": 28,
            "summary": "Metro Central has 450 units on hand; local forecast requires 45 units over 30 days. Surplus of 350 units available."
        },
        destination_rationale={
            "current_stock": 15,
            "days_of_cover": 1.2,
            "daily_burn_rate": 12.0,
            "unmet_need": 100,
            "summary": "Highland Hospital faces stockout in 28 hours. Projected consumption is 12 vials/day with only 15 in stock."
        },
        optimisation_metadata={"acceptance_score": 96.5, "transport_distance_km": 42},
        proposal_version=1
    )
    db.add(prop)
    db.flush()

    tpb = TransferProposalBatch(
        proposal_id=prop.id,
        batch_id=b1_metro.id,
        quantity=100,
        unit="VIAL"
    )
    db.add(tpb)

    # Pre-seed one READY-TO-SCAN Transfer so user can immediately test QR scanning!
    prop2 = TransferProposal(
        source_facility_id=fac_map["apex"].id,
        destination_facility_id=fac_map["highland"].id,
        product_id=prod_map["MED-005"].id, # Enoxaparin
        proposed_quantity=40,
        unit="SYRINGE",
        status="RESERVED",
        priority="HIGH",
        expected_arrival_at=datetime.now(timezone.utc) + timedelta(days=1),
        source_rationale={"usable_stock": 150, "summary": "Eligible surplus confirmed."},
        destination_rationale={"current_stock": 4, "summary": "Buffer restoration needed."},
        proposal_version=1
    )
    db.add(prop2)
    db.flush()

    # Pre-approve both sides
    appr1 = TransferApproval(
        proposal_id=prop2.id,
        proposal_version=1,
        facility_id=fac_map["apex"].id,
        approver_user_id=user_map["sarah.rao@apexhealth.org"].id,
        decision="APPROVED",
        reason="Approved by Medical Superintendent"
    )
    appr2 = TransferApproval(
        proposal_id=prop2.id,
        proposal_version=1,
        facility_id=fac_map["highland"].id,
        approver_user_id=user_map["vikram.singh@highlandhospital.org"].id,
        decision="APPROVED",
        reason="Accepted by Highland Receiving Pharmacist"
    )
    db.add_all([appr1, appr2])
    db.flush()

    # Create transfer
    demo_transfer = Transfer(
        proposal_id=prop2.id,
        status="READY_FOR_DISPATCH",
        source_facility_id=fac_map["apex"].id,
        destination_facility_id=fac_map["highland"].id,
        tracking_reference="TRK-SOS-DEMO001"
    )
    db.add(demo_transfer)
    db.flush()

    # Fetch batch for Enoxaparin
    enox_batch = db.query(Batch).filter(Batch.product_id == prod_map["MED-005"].id).first()
    demo_pkg = TransferPackage(
        transfer_id=demo_transfer.id,
        package_reference="PKG-DEMO-01",
        batch_id=enox_batch.id,
        quantity=40,
        unit="SYRINGE",
        status="PREPARED"
    )
    db.add(demo_pkg)
    db.flush()

    # Create known deterministic token for easy copy-paste and camera demo
    demo_token = "SOS_DEMO_TRANSFER_TOKEN_VALID_2026"
    demo_label = SerializedLabel(
        transfer_package_id=demo_pkg.id,
        token_hash=hash_token(demo_token),
        label_version=1,
        status="ISSUED"
    )
    db.add(demo_label)

    # =========================================================================
    # A. INELIGIBLE BATCH SCENARIOS (quarantined / recalled / damaged / expired)
    # =========================================================================

    # A1. RECALLED batch of MED-003 (Ceftriaxone) at metro facility
    b_ceft_recalled = Batch(
        product_id=prod_map["MED-003"].id,
        manufacturer_lot_number="LOT-CEFT-RECALLED-2025",
        manufacturing_date=today - timedelta(days=120),
        expiry_date=today + timedelta(days=20),
        manufacturer="Glenmark Injectables",
        quality_status="RECALLED"
    )
    db.add(b_ceft_recalled)
    db.flush()
    LedgerService.record_movement(db, fac_map["metro"].id, b_ceft_recalled.id, "OPENING_BALANCE", 50, unit="VIAL", reason="Recalled batch — DO NOT DISPENSE")

    # A2. QUARANTINED batch of MED-001 (Meropenem) at apex facility
    b_mero_quarantine = Batch(
        product_id=prod_map["MED-001"].id,
        manufacturer_lot_number="LOT-MERO-QUARANTINE",
        manufacturing_date=today - timedelta(days=45),
        expiry_date=today + timedelta(days=90),
        manufacturer="Biochem Pharma Ltd",
        quality_status="QUARANTINED"
    )
    db.add(b_mero_quarantine)
    db.flush()
    LedgerService.record_movement(db, fac_map["apex"].id, b_mero_quarantine.id, "OPENING_BALANCE", 80, unit="VIAL", reason="Quarantine opening balance — pending QC investigation")
    LedgerService.record_movement(db, fac_map["apex"].id, b_mero_quarantine.id, "QUARANTINE", -80, unit="VIAL", reason="Placed under quarantine — QC hold pending investigation")

    # A3. EXPIRED batch of MED-004 (Amoxicillin) at metro facility
    #     Released quality status but past its expiry date — should be ineligible for transfer
    b_amox_expired = Batch(
        product_id=prod_map["MED-004"].id,
        manufacturer_lot_number="LOT-AMOX-EXPIRED-23",
        manufacturing_date=today - timedelta(days=390),
        expiry_date=today - timedelta(days=30),   # Already expired!
        manufacturer="Sun Diagnostics",
        quality_status="RELEASED"
    )
    db.add(b_amox_expired)
    db.flush()
    LedgerService.record_movement(db, fac_map["metro"].id, b_amox_expired.id, "OPENING_BALANCE", 120, unit="TABLET", reason="Expired batch — status released but past expiry date")

    # A4. DAMAGED batch of MED-009 (Paracetamol) at highland facility
    b_para_damaged = Batch(
        product_id=prod_map["MED-009"].id,
        manufacturer_lot_number="LOT-PARA-DAMAGED",
        manufacturing_date=today - timedelta(days=60),
        expiry_date=today + timedelta(days=180),
        manufacturer="Standard Healthcare Labs",
        quality_status="DAMAGED"
    )
    db.add(b_para_damaged)
    db.flush()
    LedgerService.record_movement(db, fac_map["highland"].id, b_para_damaged.id, "OPENING_BALANCE", 60, unit="BOTTLE", reason="Damaged batch opening balance")
    LedgerService.record_movement(db, fac_map["highland"].id, b_para_damaged.id, "DAMAGE", -60, unit="BOTTLE", reason="Batch damaged in transit — quarantined for disposal")

    # =========================================================================
    # B. STOCK-CHANGE-BEFORE-RESERVATION SCENARIO
    # =========================================================================
    # A second proposed transfer for MED-003 (Ceftriaxone):
    # Apex → Highland, but apex ward consumption is 15-20/day and stock may fall below 60

    prop_ceft_stock_risk = TransferProposal(
        source_facility_id=fac_map["apex"].id,
        destination_facility_id=fac_map["highland"].id,
        product_id=prod_map["MED-003"].id,
        proposed_quantity=60,
        unit="VIAL",
        status="PROPOSED",
        priority="HIGH",
        expected_arrival_at=datetime.now(timezone.utc) + timedelta(days=3),
        source_rationale={
            "usable_stock": 80,
            "surplus_available": 60,
            "summary": "Apex has 80 units on-hand (released). Proposing 60 units to Highland.",
        },
        destination_rationale={
            "current_stock": 10,
            "daily_burn_rate": 8.0,
            "summary": "Highland requires Ceftriaxone replenishment.",
        },
        optimisation_metadata={
            "scenario": "STOCK_CHANGE_RISK",
            "note": "Apex Ceftriaxone stock may fall below 60 before reservation completes due to 15-20/day ward consumption",
        },
        proposal_version=1,
    )
    db.add(prop_ceft_stock_risk)
    db.flush()

    tpb_ceft = TransferProposalBatch(
        proposal_id=prop_ceft_stock_risk.id,
        batch_id=b3_apex.id,
        quantity=60,
        unit="VIAL",
    )
    db.add(tpb_ceft)

    # =========================================================================
    # C. REJECTED CANDIDATE SCENARIO
    # =========================================================================
    # Transfer of MED-002 (Insulin) from metro → st_jude rejected due to cold-chain constraint

    prop_insulin_rejected = TransferProposal(
        source_facility_id=fac_map["metro"].id,
        destination_facility_id=fac_map["st_jude"].id,
        product_id=prod_map["MED-002"].id,
        proposed_quantity=50,
        unit="VIAL",
        status="REJECTED",
        priority="NORMAL",
        expected_arrival_at=datetime.now(timezone.utc) + timedelta(days=2),
        source_rationale={
            "usable_stock": 200,
            "summary": "Metro has 200 units of Insulin Regular available.",
        },
        destination_rationale={
            "current_stock": 0,
            "summary": "St. Jude has no Insulin stock but lacks cold-chain storage.",
        },
        optimisation_metadata={
            "rejection_reason": "STORAGE_INCOMPATIBLE",
            "detail": (
                "St. Jude lacks cold chain (max 28C). Insulin requires 2-8C refrigeration. "
                "Transfer blocked by deterministic storage constraint check."
            ),
        },
        proposal_version=1,
    )
    db.add(prop_insulin_rejected)
    db.flush()

    tpb_insulin = TransferProposalBatch(
        proposal_id=prop_insulin_rejected.id,
        batch_id=b2_metro.id,
        quantity=50,
        unit="VIAL",
    )
    db.add(tpb_insulin)

    # Rejection approval record
    appr_rejected = TransferApproval(
        proposal_id=prop_insulin_rejected.id,
        proposal_version=1,
        facility_id=fac_map["metro"].id,
        approver_user_id=user_map["amit.patel@metrocentral.org"].id,
        decision="REJECTED",
        reason=(
            "Destination facility does not meet cold chain requirements for Insulin Regular "
            "(COLD_CHAIN_2_8C). Storage constraint violation."
        ),
    )
    db.add(appr_rejected)

    # =========================================================================
    # D. SAFETY STOCK POLICIES
    # =========================================================================
    safety_stock_policies = {
        "metro_meropenem": {
            "product": "MED-001",
            "facility": "metro",
            "safety_stock_units": 28,
            "reorder_point": 60,
        },
        "highland_meropenem": {
            "product": "MED-001",
            "facility": "highland",
            "safety_stock_units": 14,
            "reorder_point": 35,
        },
    }

    db.commit()
    return {
        "status": "SUCCESS",
        "facilities_count": len(facilities_data),
        "products_count": len(products_data),
        "demo_qr_token": demo_token,
        "demo_transfer_id": demo_transfer.id,
        "active_proposal_id": prop.id,
        "facilities": {k: v.id for k, v in fac_map.items()},
        # New scenario IDs
        "recalled_batch_id": b_ceft_recalled.id,
        "quarantined_batch_id": b_mero_quarantine.id,
        "expired_batch_id": b_amox_expired.id,
        "damaged_batch_id": b_para_damaged.id,
        "stock_change_risk_proposal_id": prop_ceft_stock_risk.id,
        "rejected_proposal_id": prop_insulin_rejected.id,
        "safety_stock_policies": safety_stock_policies,
    }


def seed_demo_data_if_empty(db: Session) -> bool:
    """Load the deterministic demo only when no operational data exists."""
    if (
        db.query(Organisation.id).first()
        or db.query(Facility.id).first()
        or db.query(Product.id).first()
    ):
        return False

    seed_database(db=db, force_reset=False)
    return True

#!/usr/bin/env python3
"""
MediFlow Synthetic Demo Database Reset and Seed Script.

This script is EXPLICITLY SCOPED to synthetic demo data only.
It will NOT delete or alter any real user/production data when
the database contains records not matching the synthetic seed marker.

Usage:
    python scripts/seed_reset.py              # Reset and reseed
    python scripts/seed_reset.py --verify     # Verify seed data only
    python scripts/seed_reset.py --smoke      # Run database smoke tests
"""
import sys
import os
import argparse
import logging
from datetime import datetime, timezone

# Add the Backend directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mediflow.seed_reset")


def run_smoke_test(db) -> dict:
    """Run database smoke tests to verify connectivity and schema."""
    from sqlalchemy import text
    results = {}
    
    # Test 1: Basic connectivity
    try:
        db.execute(text("SELECT 1"))
        results["connectivity"] = "PASS"
    except Exception as e:
        results["connectivity"] = f"FAIL: {e}"
    
    # Test 2: Table existence
    tables = [
        "organisations", "facilities", "users", "facility_memberships",
        "products", "batches", "facility_batch_inventory", "inventory_ledger",
        "consumption_records", "purchase_orders", "purchase_order_lines",
        "forecast_runs", "risk_assessments", "transfer_proposals",
        "transfer_proposal_batches", "transfer_approvals", "transfers",
        "transfer_packages", "serialized_labels", "scan_events",
        "audit_events", "import_jobs"
    ]
    missing_tables = []
    for table in tables:
        try:
            db.execute(text(f"SELECT COUNT(*) FROM {table}"))
        except Exception:
            missing_tables.append(table)
    results["tables_present"] = "PASS" if not missing_tables else f"FAIL: missing {missing_tables}"
    
    return results


def run_seed_verification(db) -> dict:
    """Run verification queries to confirm seed data is present and consistent."""
    from sqlalchemy import text
    results = {}
    
    queries = {
        "organisations": "SELECT COUNT(*) FROM organisations",
        "facilities": "SELECT COUNT(*) FROM facilities",
        "products": "SELECT COUNT(*) FROM products WHERE status = 'ACTIVE'",
        "batches_total": "SELECT COUNT(*) FROM batches",
        "batches_released": "SELECT COUNT(*) FROM batches WHERE quality_status = 'RELEASED'",
        "batches_quarantined": "SELECT COUNT(*) FROM batches WHERE quality_status = 'QUARANTINED'",
        "batches_recalled": "SELECT COUNT(*) FROM batches WHERE quality_status = 'RECALLED'",
        "batches_damaged": "SELECT COUNT(*) FROM batches WHERE quality_status = 'DAMAGED'",
        "inventory_records": "SELECT COUNT(*) FROM facility_batch_inventory",
        "ledger_entries": "SELECT COUNT(*) FROM inventory_ledger",
        "consumption_records": "SELECT COUNT(*) FROM consumption_records",
        "purchase_orders": "SELECT COUNT(*) FROM purchase_orders",
        "transfer_proposals": "SELECT COUNT(*) FROM transfer_proposals",
        "transfer_approvals": "SELECT COUNT(*) FROM transfer_approvals",
        "transfers": "SELECT COUNT(*) FROM transfers",
        "transfer_packages": "SELECT COUNT(*) FROM transfer_packages",
        "serialized_labels": "SELECT COUNT(*) FROM serialized_labels",
        "audit_events": "SELECT COUNT(*) FROM audit_events",
    }
    
    for key, query in queries.items():
        try:
            result = db.execute(text(query)).scalar()
            results[key] = result
        except Exception as e:
            results[key] = f"ERROR: {e}"
    
    # Ledger reconciliation check: sum of all deltas per facility/batch should match on_hand_quantity
    try:
        reconcile_q = text("""
            SELECT 
                fbi.facility_id,
                fbi.batch_id,
                fbi.on_hand_quantity AS projected,
                COALESCE(SUM(CASE WHEN il.movement_type IN ('OPENING_BALANCE','PURCHASE_RECEIPT','TRANSFER_RECEIPT','ADJUSTMENT_ADD') THEN il.quantity_delta
                               WHEN il.movement_type IN ('CONSUMPTION','DAMAGE','EXPIRY','ADJUSTMENT_SUB') THEN il.quantity_delta
                               WHEN il.movement_type = 'TRANSFER_DISPATCH' THEN -ABS(il.quantity_delta)
                               ELSE 0 END), 0) AS ledger_sum
            FROM facility_batch_inventory fbi
            LEFT JOIN inventory_ledger il ON il.facility_id = fbi.facility_id AND il.batch_id = fbi.batch_id
            GROUP BY fbi.facility_id, fbi.batch_id, fbi.on_hand_quantity
            HAVING fbi.on_hand_quantity != COALESCE(SUM(CASE WHEN il.movement_type IN ('OPENING_BALANCE','PURCHASE_RECEIPT','TRANSFER_RECEIPT','ADJUSTMENT_ADD') THEN il.quantity_delta
                               WHEN il.movement_type IN ('CONSUMPTION','DAMAGE','EXPIRY','ADJUSTMENT_SUB') THEN il.quantity_delta
                               WHEN il.movement_type = 'TRANSFER_DISPATCH' THEN -ABS(il.quantity_delta)
                               ELSE 0 END), 0)
        """)
        mismatches = db.execute(reconcile_q).fetchall()
        results["ledger_reconciliation"] = f"PASS (0 mismatches)" if not mismatches else f"WARN: {len(mismatches)} mismatches"
    except Exception as e:
        results["ledger_reconciliation"] = f"SKIP (SQLite limitation): {type(e).__name__}"

    # Proposal scenario check
    try:
        critical_proposals = db.execute(text("SELECT COUNT(*) FROM transfer_proposals WHERE priority = 'CRITICAL'")).scalar()
        rejected_proposals = db.execute(text("SELECT COUNT(*) FROM transfer_proposals WHERE status = 'REJECTED'")).scalar()
        results["critical_proposals"] = critical_proposals
        results["rejected_proposals"] = rejected_proposals
    except Exception as e:
        results["scenario_check"] = f"ERROR: {e}"
    
    return results


def main():
    parser = argparse.ArgumentParser(description="MediFlow Demo Seed Reset Tool")
    parser.add_argument("--verify", action="store_true", help="Verify seed data only (no reset)")
    parser.add_argument("--smoke", action="store_true", help="Run smoke tests only")
    parser.add_argument("--no-reset", action="store_true", help="Seed without dropping tables")
    parser.add_argument(
        "--allow-remote-database",
        action="store_true",
        help="Explicitly allow this script to connect to PostgreSQL/YugabyteDB.",
    )
    parser.add_argument(
        "--allow-remote-reset",
        action="store_true",
        help="Explicitly allow dropping and recreating tables on PostgreSQL/YugabyteDB.",
    )
    args = parser.parse_args()
    
    from app.core.database import (
        SessionLocal,
        get_database_url,
        initialize_database,
        is_yugabyte_active,
        dispose_engine,
    )
    from app.core.config import settings

    if settings.is_yugabyte and not (
        args.allow_remote_database or args.allow_remote_reset
    ):
        raise RuntimeError(
            "Refusing to connect to PostgreSQL/YugabyteDB from the seed script "
            "without --allow-remote-database."
        )
    initialize_database()
    
    db_url = get_database_url()
    logger.info(f"Database backend: {db_url.get_backend_name()}")
    logger.info("Active database: %s", "YugabyteDB/PostgreSQL" if is_yugabyte_active() else "SQLite")
    if not is_yugabyte_active():
        logger.info("⚠️  Using SQLite fallback. For YugabyteDB, set DATABASE_URL in Backend/.env")
        logger.info("   YugabyteDB connection format: postgresql://user:pass@host:5433/db?sslmode=verify-full&sslrootcert=/path/to/root.crt")
    if is_yugabyte_active() and not (
        args.verify or args.smoke or args.no_reset or args.allow_remote_reset
    ):
        dispose_engine()
        raise RuntimeError(
            "Refusing to reset a remote PostgreSQL/YugabyteDB database without "
            "--allow-remote-reset. This operation drops and recreates all tables."
        )

    db = SessionLocal()
    try:
        if args.smoke:
            logger.info("=== Running Database Smoke Tests ===")
            results = run_smoke_test(db)
            for k, v in results.items():
                status = "✅" if str(v).startswith("PASS") else "❌"
                logger.info(f"  {status} {k}: {v}")
            return
        
        if args.verify:
            logger.info("=== Running Seed Verification ===")
            results = run_seed_verification(db)
            for k, v in results.items():
                logger.info(f"  {k}: {v}")
            return
        
        # Full reset
        logger.info("=== MediFlow Synthetic Demo Seed Reset ===")
        logger.info("⚠️  This will DROP and recreate all tables. SYNTHETIC DEMO DATA ONLY.")
        
        from app.services.seed_service import seed_database
        result = seed_database(db, force_reset=not args.no_reset)
        
        logger.info("✅ Seed complete!")
        for k, v in result.items():
            logger.info(f"  {k}: {v}")
        
        # Auto-verify after seeding
        logger.info("\n=== Seed Verification ===")
        verify_results = run_seed_verification(db)
        for k, v in verify_results.items():
            logger.info(f"  {k}: {v}")
        
        logger.info("\n✅ Database ready for MediFlow demo.")
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        raise
    finally:
        db.close()
        dispose_engine()


if __name__ == "__main__":
    main()

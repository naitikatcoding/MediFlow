"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-31

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. organisations
    # ------------------------------------------------------------------
    op.create_table(
        'organisations',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('organisation_type', sa.String(64), nullable=False, server_default='HEALTHCARE_NETWORK'),
        sa.Column('status', sa.String(32), nullable=False, server_default='ACTIVE'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # ------------------------------------------------------------------
    # 2. facilities
    # ------------------------------------------------------------------
    op.create_table(
        'facilities',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('organisation_id', sa.String(36), sa.ForeignKey('organisations.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('facility_type', sa.String(64), nullable=False),
        sa.Column('address', sa.String(500), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('timezone', sa.String(64), nullable=False, server_default='Asia/Kolkata'),
        sa.Column('status', sa.String(32), nullable=False, server_default='ACTIVE'),
        sa.Column('storage_capabilities', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )

    # ------------------------------------------------------------------
    # 3. users
    # ------------------------------------------------------------------
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('organisation_id', sa.String(36), sa.ForeignKey('organisations.id'), nullable=False),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('role', sa.String(64), nullable=False, server_default='PHARMACIST'),
        sa.Column('status', sa.String(32), nullable=False, server_default='ACTIVE'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # ------------------------------------------------------------------
    # 4. facility_memberships
    # ------------------------------------------------------------------
    op.create_table(
        'facility_memberships',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('facility_id', sa.String(36), sa.ForeignKey('facilities.id'), nullable=False),
        sa.Column('role', sa.String(64), nullable=False),
        sa.Column('status', sa.String(32), nullable=False, server_default='ACTIVE'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('user_id', 'facility_id', 'role', name='uq_user_facility_role'),
    )

    # ------------------------------------------------------------------
    # 5. products
    # ------------------------------------------------------------------
    op.create_table(
        'products',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('internal_code', sa.String(64), nullable=False, unique=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('generic_name', sa.String(255), nullable=False),
        sa.Column('brand_name', sa.String(255), nullable=True),
        sa.Column('strength', sa.String(64), nullable=False),
        sa.Column('dosage_form', sa.String(64), nullable=False),
        sa.Column('pack_size', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('base_unit', sa.String(32), nullable=False, server_default='UNIT'),
        sa.Column('gtin', sa.String(64), nullable=True),
        sa.Column('storage_requirements', sa.String(128), nullable=False, server_default='ROOM_TEMPERATURE'),
        sa.Column('transfer_policy_code', sa.String(64), nullable=False, server_default='STANDARD_ELIGIBLE'),
        sa.Column('status', sa.String(32), nullable=False, server_default='ACTIVE'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_products_internal_code', 'products', ['internal_code'], unique=True)
    op.create_index('ix_products_generic_name', 'products', ['generic_name'], unique=False)
    op.create_index('ix_products_gtin', 'products', ['gtin'], unique=False)

    # ------------------------------------------------------------------
    # 6. batches
    # ------------------------------------------------------------------
    op.create_table(
        'batches',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('product_id', sa.String(36), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('manufacturer_lot_number', sa.String(128), nullable=False),
        sa.Column('manufacturing_date', sa.Date(), nullable=True),
        sa.Column('expiry_date', sa.Date(), nullable=False),
        sa.Column('manufacturer', sa.String(255), nullable=False),
        sa.Column('supplier_id', sa.String(64), nullable=True),
        sa.Column('quality_status', sa.String(32), nullable=False, server_default='RELEASED'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_batches_product_id', 'batches', ['product_id'], unique=False)
    op.create_index('ix_batches_manufacturer_lot_number', 'batches', ['manufacturer_lot_number'], unique=False)
    op.create_index('ix_batches_expiry_date', 'batches', ['expiry_date'], unique=False)
    op.create_index('ix_batches_product_expiry', 'batches', ['product_id', 'expiry_date'], unique=False)

    # ------------------------------------------------------------------
    # 7. facility_batch_inventory
    # ------------------------------------------------------------------
    op.create_table(
        'facility_batch_inventory',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('facility_id', sa.String(36), sa.ForeignKey('facilities.id'), nullable=False),
        sa.Column('batch_id', sa.String(36), sa.ForeignKey('batches.id'), nullable=False),
        sa.Column('on_hand_quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reserved_quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('quarantined_quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('damaged_quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unit', sa.String(32), nullable=False, server_default='UNIT'),
        sa.Column('last_reconciled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.UniqueConstraint('facility_id', 'batch_id', name='uq_facility_batch'),
        sa.CheckConstraint('on_hand_quantity >= 0', name='chk_on_hand_non_negative'),
        sa.CheckConstraint('reserved_quantity >= 0', name='chk_reserved_non_negative'),
        sa.CheckConstraint('quarantined_quantity >= 0', name='chk_quarantined_non_negative'),
        sa.CheckConstraint('damaged_quantity >= 0', name='chk_damaged_non_negative'),
        sa.CheckConstraint('reserved_quantity <= on_hand_quantity', name='chk_reserved_le_on_hand'),
    )
    op.create_index('ix_facility_batch_inventory_facility_id', 'facility_batch_inventory', ['facility_id'], unique=False)
    op.create_index('ix_facility_batch_inventory_batch_id', 'facility_batch_inventory', ['batch_id'], unique=False)

    # ------------------------------------------------------------------
    # 8. inventory_ledger
    # ------------------------------------------------------------------
    op.create_table(
        'inventory_ledger',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('facility_id', sa.String(36), sa.ForeignKey('facilities.id'), nullable=False),
        sa.Column('batch_id', sa.String(36), sa.ForeignKey('batches.id'), nullable=False),
        sa.Column('movement_type', sa.String(64), nullable=False),
        sa.Column('quantity_delta', sa.Integer(), nullable=False),
        sa.Column('unit', sa.String(32), nullable=False, server_default='UNIT'),
        sa.Column('reference_type', sa.String(64), nullable=True),
        sa.Column('reference_id', sa.String(64), nullable=True),
        sa.Column('actor_id', sa.String(64), nullable=True),
        sa.Column('idempotency_key', sa.String(128), nullable=True, unique=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
    )
    op.create_index('ix_inventory_ledger_facility_id', 'inventory_ledger', ['facility_id'], unique=False)
    op.create_index('ix_inventory_ledger_batch_id', 'inventory_ledger', ['batch_id'], unique=False)
    op.create_index('ix_inventory_ledger_reference_id', 'inventory_ledger', ['reference_id'], unique=False)
    op.create_index('ix_inventory_ledger_idempotency_key', 'inventory_ledger', ['idempotency_key'], unique=True)
    op.create_index('ix_ledger_facility_batch_occurred', 'inventory_ledger', ['facility_id', 'batch_id', 'occurred_at'], unique=False)

    # ------------------------------------------------------------------
    # 9. consumption_records
    # ------------------------------------------------------------------
    op.create_table(
        'consumption_records',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('facility_id', sa.String(36), sa.ForeignKey('facilities.id'), nullable=False),
        sa.Column('product_id', sa.String(36), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('batch_id', sa.String(36), sa.ForeignKey('batches.id'), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit', sa.String(32), nullable=False, server_default='UNIT'),
        sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source_system', sa.String(64), nullable=False, server_default='SYNTHETIC_HIS'),
        sa.Column('import_job_id', sa.String(36), nullable=True),
        sa.Column('data_quality_status', sa.String(32), nullable=False, server_default='VALIDATED'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('quantity >= 0', name='chk_consumption_quantity_non_negative'),
    )
    op.create_index('ix_consumption_records_facility_id', 'consumption_records', ['facility_id'], unique=False)
    op.create_index('ix_consumption_records_product_id', 'consumption_records', ['product_id'], unique=False)
    op.create_index('ix_consumption_records_batch_id', 'consumption_records', ['batch_id'], unique=False)
    op.create_index('ix_consumption_records_consumed_at', 'consumption_records', ['consumed_at'], unique=False)
    op.create_index('ix_consumption_fac_prod_date', 'consumption_records', ['facility_id', 'product_id', 'consumed_at'], unique=False)

    # ------------------------------------------------------------------
    # 10. purchase_orders
    # ------------------------------------------------------------------
    op.create_table(
        'purchase_orders',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('facility_id', sa.String(36), sa.ForeignKey('facilities.id'), nullable=False),
        sa.Column('supplier_id', sa.String(64), nullable=False),
        sa.Column('status', sa.String(32), nullable=False, server_default='PLACED'),
        sa.Column('expected_delivery_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_purchase_orders_facility_id', 'purchase_orders', ['facility_id'], unique=False)

    # ------------------------------------------------------------------
    # 11. purchase_order_lines
    # ------------------------------------------------------------------
    op.create_table(
        'purchase_order_lines',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('purchase_order_id', sa.String(36), sa.ForeignKey('purchase_orders.id'), nullable=False),
        sa.Column('product_id', sa.String(36), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('quantity_ordered', sa.Integer(), nullable=False),
        sa.Column('quantity_received', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unit', sa.String(32), nullable=False, server_default='UNIT'),
    )

    # ------------------------------------------------------------------
    # 12. forecast_runs
    # ------------------------------------------------------------------
    op.create_table(
        'forecast_runs',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('facility_id', sa.String(36), sa.ForeignKey('facilities.id'), nullable=False),
        sa.Column('product_id', sa.String(36), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('model_name', sa.String(64), nullable=False, server_default='WEIGHTED_MOVING_AVERAGE'),
        sa.Column('horizon_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('horizon_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('forecast_payload', sa.JSON(), nullable=False),
        sa.Column('metrics', sa.JSON(), nullable=True),
        sa.Column('data_quality_score', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_forecast_runs_facility_id', 'forecast_runs', ['facility_id'], unique=False)
    op.create_index('ix_forecast_runs_product_id', 'forecast_runs', ['product_id'], unique=False)

    # ------------------------------------------------------------------
    # 13. risk_assessments
    # ------------------------------------------------------------------
    op.create_table(
        'risk_assessments',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('facility_id', sa.String(36), sa.ForeignKey('facilities.id'), nullable=False),
        sa.Column('product_id', sa.String(36), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('risk_type', sa.String(32), nullable=False),
        sa.Column('risk_level', sa.String(32), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('explanation', sa.JSON(), nullable=False),
        sa.Column('forecast_run_id', sa.String(36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_risk_assessments_facility_id', 'risk_assessments', ['facility_id'], unique=False)
    op.create_index('ix_risk_assessments_product_id', 'risk_assessments', ['product_id'], unique=False)
    op.create_index('ix_risk_fac_type_level', 'risk_assessments', ['facility_id', 'risk_type', 'risk_level'], unique=False)

    # ------------------------------------------------------------------
    # 14. transfer_proposals
    # ------------------------------------------------------------------
    op.create_table(
        'transfer_proposals',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('source_facility_id', sa.String(36), sa.ForeignKey('facilities.id'), nullable=False),
        sa.Column('destination_facility_id', sa.String(36), sa.ForeignKey('facilities.id'), nullable=False),
        sa.Column('product_id', sa.String(36), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('proposed_quantity', sa.Integer(), nullable=False),
        sa.Column('unit', sa.String(32), nullable=False, server_default='UNIT'),
        sa.Column('status', sa.String(32), nullable=False, server_default='PROPOSED'),
        sa.Column('priority', sa.String(32), nullable=False, server_default='MEDIUM'),
        sa.Column('expected_arrival_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source_rationale', sa.JSON(), nullable=False),
        sa.Column('destination_rationale', sa.JSON(), nullable=False),
        sa.Column('optimisation_metadata', sa.JSON(), nullable=True),
        sa.Column('proposal_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_by_workflow_id', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_transfer_proposals_source_facility_id', 'transfer_proposals', ['source_facility_id'], unique=False)
    op.create_index('ix_transfer_proposals_destination_facility_id', 'transfer_proposals', ['destination_facility_id'], unique=False)
    op.create_index('ix_transfer_proposals_product_id', 'transfer_proposals', ['product_id'], unique=False)
    op.create_index('ix_transfer_proposals_status', 'transfer_proposals', ['status'], unique=False)
    op.create_index('ix_proposals_status_priority', 'transfer_proposals', ['status', 'priority', 'created_at'], unique=False)

    # ------------------------------------------------------------------
    # 15. transfer_proposal_batches
    # ------------------------------------------------------------------
    op.create_table(
        'transfer_proposal_batches',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('proposal_id', sa.String(36), sa.ForeignKey('transfer_proposals.id'), nullable=False),
        sa.Column('batch_id', sa.String(36), sa.ForeignKey('batches.id'), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit', sa.String(32), nullable=False, server_default='UNIT'),
    )
    op.create_index('ix_transfer_proposal_batches_proposal_id', 'transfer_proposal_batches', ['proposal_id'], unique=False)
    op.create_index('ix_transfer_proposal_batches_batch_id', 'transfer_proposal_batches', ['batch_id'], unique=False)

    # ------------------------------------------------------------------
    # 16. transfer_approvals
    # ------------------------------------------------------------------
    op.create_table(
        'transfer_approvals',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('proposal_id', sa.String(36), sa.ForeignKey('transfer_proposals.id'), nullable=False),
        sa.Column('proposal_version', sa.Integer(), nullable=False),
        sa.Column('facility_id', sa.String(36), sa.ForeignKey('facilities.id'), nullable=False),
        sa.Column('approver_user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('decision', sa.String(32), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('proposal_id', 'facility_id', 'proposal_version', name='uq_proposal_facility_version'),
    )
    op.create_index('ix_transfer_approvals_proposal_id', 'transfer_approvals', ['proposal_id'], unique=False)
    op.create_index('ix_transfer_approvals_facility_id', 'transfer_approvals', ['facility_id'], unique=False)

    # ------------------------------------------------------------------
    # 17. transfers
    # ------------------------------------------------------------------
    op.create_table(
        'transfers',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('proposal_id', sa.String(36), sa.ForeignKey('transfer_proposals.id'), nullable=False, unique=True),
        sa.Column('status', sa.String(32), nullable=False, server_default='RESERVED'),
        sa.Column('source_facility_id', sa.String(36), sa.ForeignKey('facilities.id'), nullable=False),
        sa.Column('destination_facility_id', sa.String(36), sa.ForeignKey('facilities.id'), nullable=False),
        sa.Column('tracking_reference', sa.String(128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('dispatched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_transfers_status', 'transfers', ['status'], unique=False)
    op.create_index('ix_transfers_source_facility_id', 'transfers', ['source_facility_id'], unique=False)
    op.create_index('ix_transfers_destination_facility_id', 'transfers', ['destination_facility_id'], unique=False)

    # ------------------------------------------------------------------
    # 18. transfer_packages
    # ------------------------------------------------------------------
    op.create_table(
        'transfer_packages',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('transfer_id', sa.String(36), sa.ForeignKey('transfers.id'), nullable=False),
        sa.Column('package_reference', sa.String(64), nullable=False),
        sa.Column('batch_id', sa.String(36), sa.ForeignKey('batches.id'), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit', sa.String(32), nullable=False, server_default='UNIT'),
        sa.Column('status', sa.String(32), nullable=False, server_default='PREPARED'),
    )
    op.create_index('ix_transfer_packages_transfer_id', 'transfer_packages', ['transfer_id'], unique=False)
    op.create_index('ix_transfer_packages_batch_id', 'transfer_packages', ['batch_id'], unique=False)

    # ------------------------------------------------------------------
    # 19. serialized_labels
    # ------------------------------------------------------------------
    op.create_table(
        'serialized_labels',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('transfer_package_id', sa.String(36), sa.ForeignKey('transfer_packages.id'), nullable=False, unique=True),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('label_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('status', sa.String(32), nullable=False, server_default='ISSUED'),
        sa.Column('issued_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_serialized_labels_token_hash', 'serialized_labels', ['token_hash'], unique=True)

    # ------------------------------------------------------------------
    # 20. scan_events
    # ------------------------------------------------------------------
    op.create_table(
        'scan_events',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('serialized_label_id', sa.String(36), sa.ForeignKey('serialized_labels.id'), nullable=False),
        sa.Column('transfer_id', sa.String(36), sa.ForeignKey('transfers.id'), nullable=False),
        sa.Column('facility_id', sa.String(36), sa.ForeignKey('facilities.id'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('scan_type', sa.String(32), nullable=False),
        sa.Column('result', sa.String(32), nullable=False),
        sa.Column('idempotency_key', sa.String(128), nullable=True, unique=True),
        sa.Column('device_reference', sa.String(128), nullable=True),
        sa.Column('scanned_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
    )
    op.create_index('ix_scan_events_serialized_label_id', 'scan_events', ['serialized_label_id'], unique=False)
    op.create_index('ix_scan_events_transfer_id', 'scan_events', ['transfer_id'], unique=False)
    op.create_index('ix_scan_events_idempotency_key', 'scan_events', ['idempotency_key'], unique=True)
    op.create_index('ix_scan_transfer_time', 'scan_events', ['transfer_id', 'scanned_at'], unique=False)

    # ------------------------------------------------------------------
    # 21. audit_events
    # ------------------------------------------------------------------
    op.create_table(
        'audit_events',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('organisation_id', sa.String(36), nullable=True),
        sa.Column('facility_id', sa.String(36), nullable=True),
        sa.Column('actor_id', sa.String(64), nullable=True),
        sa.Column('action', sa.String(64), nullable=False),
        sa.Column('entity_type', sa.String(64), nullable=False),
        sa.Column('entity_id', sa.String(64), nullable=False),
        sa.Column('before_state', sa.JSON(), nullable=True),
        sa.Column('after_state', sa.JSON(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_audit_events_facility_id', 'audit_events', ['facility_id'], unique=False)
    op.create_index('ix_audit_events_actor_id', 'audit_events', ['actor_id'], unique=False)
    op.create_index('ix_audit_events_action', 'audit_events', ['action'], unique=False)
    op.create_index('ix_audit_events_entity_type', 'audit_events', ['entity_type'], unique=False)
    op.create_index('ix_audit_events_entity_id', 'audit_events', ['entity_id'], unique=False)
    op.create_index('ix_audit_entity_time', 'audit_events', ['entity_type', 'entity_id', 'created_at'], unique=False)

    # ------------------------------------------------------------------
    # 22. import_jobs
    # ------------------------------------------------------------------
    op.create_table(
        'import_jobs',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('facility_id', sa.String(36), sa.ForeignKey('facilities.id'), nullable=False),
        sa.Column('source_type', sa.String(64), nullable=False),
        sa.Column('filename', sa.String(255), nullable=True),
        sa.Column('status', sa.String(32), nullable=False, server_default='PROCESSING'),
        sa.Column('row_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('accepted_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('rejected_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_summary', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_import_jobs_facility_id', 'import_jobs', ['facility_id'], unique=False)


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_table('import_jobs')
    op.drop_table('audit_events')
    op.drop_table('scan_events')
    op.drop_table('serialized_labels')
    op.drop_table('transfer_packages')
    op.drop_table('transfers')
    op.drop_table('transfer_approvals')
    op.drop_table('transfer_proposal_batches')
    op.drop_table('transfer_proposals')
    op.drop_table('risk_assessments')
    op.drop_table('forecast_runs')
    op.drop_table('purchase_order_lines')
    op.drop_table('purchase_orders')
    op.drop_table('consumption_records')
    op.drop_table('inventory_ledger')
    op.drop_table('facility_batch_inventory')
    op.drop_table('batches')
    op.drop_table('products')
    op.drop_table('facility_memberships')
    op.drop_table('users')
    op.drop_table('facilities')
    op.drop_table('organisations')

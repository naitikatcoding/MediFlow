"""Add correlation IDs to audit events.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None
def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("audit_events")}
    if "correlation_id" not in columns:
        op.add_column("audit_events", sa.Column("correlation_id", sa.String(64), nullable=True))

    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("audit_events")}
    if "ix_audit_correlation" not in indexes:
        op.create_index(
            "ix_audit_correlation",
            "audit_events",
            ["correlation_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("audit_events")}
    if "ix_audit_correlation" in indexes:
        op.drop_index("ix_audit_correlation", table_name="audit_events")

    columns = {column["name"] for column in sa.inspect(bind).get_columns("audit_events")}
    if "correlation_id" in columns:
        op.drop_column("audit_events", "correlation_id")

"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INSPECTION_STATUS = sa.Enum(
    "uploaded",
    "processing",
    "completed",
    "needs_review",
    "failed",
    name="inspection_status",
)


def upgrade() -> None:
    INSPECTION_STATUS.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "inspections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inspection_id", sa.String(length=64), nullable=False),
        sa.Column("status", INSPECTION_STATUS, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_inspections_inspection_id"), "inspections", ["inspection_id"], unique=True)

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inspection_id", sa.Integer(), nullable=False),
        sa.Column("product_name", sa.String(length=512), nullable=True),
        sa.Column("manufacturer", sa.String(length=512), nullable=True),
        sa.Column("net_quantity", sa.String(length=128), nullable=True),
        sa.Column("mrp", sa.Numeric(10, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspections.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inspection_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspections.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("products")
    op.drop_index(op.f("ix_inspections_inspection_id"), table_name="inspections")
    op.drop_table("inspections")
    INSPECTION_STATUS.drop(op.get_bind(), checkfirst=True)

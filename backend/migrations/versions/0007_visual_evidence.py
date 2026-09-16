"""phase 7: visual evidence provenance

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "visual_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("inspection_id", sa.Integer(), sa.ForeignKey("inspections.id"), nullable=False, index=True),
        sa.Column("evidence_id", sa.String(length=32), nullable=False, index=True),
        sa.Column("evidence_type", sa.String(length=32), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("bbox_json", sa.JSON(), nullable=True),
        sa.Column("value_numeric", sa.Numeric(14, 4), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("method", sa.String(length=64), nullable=False),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("ocr_block_id", sa.String(length=32), nullable=True),
        sa.Column("ocr_block_ids", sa.JSON(), nullable=True),
        sa.Column("field_name", sa.String(length=64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("visual_evidence")

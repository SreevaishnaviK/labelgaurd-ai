"""phase 3: structured field extraction

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "extracted_fields",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("inspection_id", sa.Integer(), nullable=False, index=True),
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.Column("candidates_json", sa.JSON(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("ocr_confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("extraction_confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspections.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "extracted_field_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("extracted_field_id", sa.Integer(), nullable=False, index=True),
        sa.Column("ocr_block_id", sa.String(length=32), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["extracted_field_id"], ["extracted_fields.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("extracted_field_evidence")
    op.drop_table("extracted_fields")

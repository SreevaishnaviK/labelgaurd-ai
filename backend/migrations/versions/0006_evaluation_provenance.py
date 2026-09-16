"""phase 6: immutable compliance evaluation provenance

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "inspection_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("inspection_id", sa.Integer(), sa.ForeignKey("inspections.id"), nullable=False, index=True),
        sa.Column("evaluation_version", sa.Integer(), nullable=False),
        sa.Column("engine_version", sa.String(length=32), nullable=False),
        sa.Column("overall_status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "rule_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "inspection_evaluation_id",
            sa.Integer(),
            sa.ForeignKey("inspection_evaluations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("rule_id", sa.String(length=32), nullable=False),
        sa.Column("rule_number", sa.String(length=32), nullable=False),
        sa.Column("rule_title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("finding", sa.Text(), nullable=False),
        sa.Column("required_information", sa.JSON(), nullable=True),
        sa.Column("actual_information", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("requires_officer_verification", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "rule_evaluation_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "rule_evaluation_id",
            sa.Integer(),
            sa.ForeignKey("rule_evaluations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("evidence_type", sa.String(length=32), nullable=False),
        sa.Column("evidence_reference", sa.String(length=255), nullable=True),
        sa.Column("ocr_block_id", sa.String(length=32), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("extracted_field_id", sa.Integer(), sa.ForeignKey("extracted_fields.id"), nullable=True),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("rule_evaluation_evidence")
    op.drop_table("rule_evaluations")
    op.drop_table("inspection_evaluations")

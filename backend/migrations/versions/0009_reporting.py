"""phase 9: reporting, inspection history and export

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "inspection_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("inspection_id", sa.Integer(), sa.ForeignKey("inspections.id"), nullable=False, index=True),
        sa.Column(
            "evaluation_id",
            sa.Integer(),
            sa.ForeignKey("inspection_evaluations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("evaluation_version", sa.Integer(), nullable=False),
        # SHA-256 of the PDF bytes — file integrity only, NOT a digital signature.
        sa.Column("report_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_reference", sa.String(length=1024), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("inspection_reports")

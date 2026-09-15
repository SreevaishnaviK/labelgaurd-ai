"""phase 4: extraction provenance

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-15

New ExtractedField columns (ai_confidence, resolution_status) plus a
normalized ExtractionCandidate table preserving every competing reading
(deterministic vs AI-assisted) with its own evidence rows. Existing Phase 3
data is untouched — all additions are nullable or new tables.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("extracted_fields", sa.Column("ai_confidence", sa.Numeric(5, 2), nullable=True))
    op.add_column("extracted_fields", sa.Column("resolution_status", sa.String(length=32), nullable=True))
    op.create_table(
        "extraction_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("extracted_field_id", sa.Integer(), nullable=False, index=True),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["extracted_field_id"], ["extracted_fields.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("extraction_candidates")
    op.drop_column("extracted_fields", "resolution_status")
    op.drop_column("extracted_fields", "ai_confidence")

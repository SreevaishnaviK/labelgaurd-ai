"""OCR multi-pass provenance (Phase 9B).

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-18

Adds source_pass to ocr_blocks so every persisted block records which OCR
pass produced it ("A" = base pipeline; "B"/"C" = recovery passes). History
stays intact: existing rows are labelled "A" — pass A output was never
altered by the recovery passes.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | None = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ocr_blocks", sa.Column("source_pass", sa.String(2), nullable=True))
    op.execute("UPDATE ocr_blocks SET source_pass = 'A' WHERE source_pass IS NULL")
    op.create_index("ix_ocr_blocks_source_pass", "ocr_blocks", ["source_pass"])


def downgrade() -> None:
    op.drop_index("ix_ocr_blocks_source_pass", table_name="ocr_blocks")
    op.drop_column("ocr_blocks", "source_pass")

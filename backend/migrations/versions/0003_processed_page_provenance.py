"""phase 2.1: processed page image provenance

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ocr_documents", sa.Column("processed_path", sa.String(length=1024), nullable=True))
    op.add_column(
        "ocr_documents",
        sa.Column("warped", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("ocr_documents", "warped")
    op.drop_column("ocr_documents", "processed_path")

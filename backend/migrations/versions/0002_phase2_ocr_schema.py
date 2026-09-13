"""phase 2: ocr schema

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PROCESSING_STATUS = sa.Enum(
    "uploaded", "processing", "processed", "failed", name="processing_status"
)


def upgrade() -> None:
    PROCESSING_STATUS.create(op.get_bind(), checkfirst=True)

    op.add_column("inspections", sa.Column("original_filename", sa.String(length=512), nullable=True))
    op.add_column("inspections", sa.Column("stored_filename", sa.String(length=255), nullable=True))
    op.add_column("inspections", sa.Column("file_path", sa.String(length=1024), nullable=True))
    op.add_column("inspections", sa.Column("mime_type", sa.String(length=128), nullable=True))
    op.add_column("inspections", sa.Column("document_type", sa.String(length=32), nullable=True))
    op.add_column("inspections", sa.Column("page_count", sa.Integer(), nullable=True))
    op.add_column(
        "inspections",
        sa.Column(
            "processing_status",
            PROCESSING_STATUS,
            nullable=False,
            server_default="uploaded",
        ),
    )

    op.create_table(
        "ocr_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inspection_id", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("full_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspections.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ocr_documents_inspection_id", "ocr_documents", ["inspection_id"])

    op.create_table(
        "ocr_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("inspection_id", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("block_id", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("block_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspections.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ocr_blocks_inspection_id", "ocr_blocks", ["inspection_id"])


def downgrade() -> None:
    op.drop_index("ix_ocr_blocks_inspection_id", table_name="ocr_blocks")
    op.drop_table("ocr_blocks")
    op.drop_index("ix_ocr_documents_inspection_id", "ocr_documents")
    op.drop_table("ocr_documents")
    op.drop_column("inspections", "processing_status")
    op.drop_column("inspections", "page_count")
    op.drop_column("inspections", "document_type")
    op.drop_column("inspections", "mime_type")
    op.drop_column("inspections", "file_path")
    op.drop_column("inspections", "stored_filename")
    op.drop_column("inspections", "original_filename")
    PROCESSING_STATUS.drop(op.get_bind(), checkfirst=True)

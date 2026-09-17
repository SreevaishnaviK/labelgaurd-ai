"""phase 8: officer verification and append-only audit

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "officer_verifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("inspection_id", sa.Integer(), sa.ForeignKey("inspections.id"), nullable=False, index=True),
        sa.Column(
            "inspection_evaluation_id",
            sa.Integer(),
            sa.ForeignKey("inspection_evaluations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("rule_evaluation_id", sa.Integer(), sa.ForeignKey("rule_evaluations.id"), nullable=False, index=True),
        sa.Column("officer_identifier", sa.String(length=255), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("evidence_ocr_block_id", sa.String(length=32), nullable=True),
        sa.Column("evidence_visual_evidence_id", sa.String(length=32), nullable=True),
        sa.Column("evidence_extracted_field_id", sa.Integer(), sa.ForeignKey("extracted_fields.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "field_verifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("inspection_id", sa.Integer(), sa.ForeignKey("inspections.id"), nullable=False, index=True),
        sa.Column("extracted_field_id", sa.Integer(), sa.ForeignKey("extracted_fields.id"), nullable=False, index=True),
        sa.Column("officer_identifier", sa.String(length=255), nullable=False),
        sa.Column("verification_status", sa.String(length=16), nullable=False),
        sa.Column("verified_value", sa.JSON(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("evidence_ocr_block_id", sa.String(length=32), nullable=True),
        sa.Column("evidence_visual_evidence_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("audit_logs", sa.Column("evaluation_id", sa.Integer(), sa.ForeignKey("inspection_evaluations.id"), nullable=True))
    op.add_column("audit_logs", sa.Column("rule_evaluation_id", sa.Integer(), sa.ForeignKey("rule_evaluations.id"), nullable=True))
    op.add_column("audit_logs", sa.Column("decision", sa.String(length=32), nullable=True))
    op.add_column("audit_logs", sa.Column("previous_state", sa.String(length=32), nullable=True))
    op.add_column("audit_logs", sa.Column("comment", sa.Text(), nullable=True))
    op.create_index("ix_audit_logs_inspection_id", "audit_logs", ["inspection_id"])
    op.create_index("ix_audit_logs_evaluation_id", "audit_logs", ["evaluation_id"])
    op.create_index("ix_audit_logs_rule_evaluation_id", "audit_logs", ["rule_evaluation_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_rule_evaluation_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_evaluation_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_inspection_id", table_name="audit_logs")
    op.drop_column("audit_logs", "comment")
    op.drop_column("audit_logs", "previous_state")
    op.drop_column("audit_logs", "decision")
    op.drop_column("audit_logs", "rule_evaluation_id")
    op.drop_column("audit_logs", "evaluation_id")
    op.drop_table("field_verifications")
    op.drop_table("officer_verifications")

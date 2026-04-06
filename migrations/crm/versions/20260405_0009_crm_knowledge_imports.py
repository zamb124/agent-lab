"""crm_knowledge_imports: журнал импорта базы знаний

Revision ID: crm_0009
Revises: crm_0008
Create Date: 2026-04-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "crm_0009"
down_revision: Union[str, None] = "crm_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crm_knowledge_imports",
        sa.Column("import_id", sa.String(length=100), nullable=False),
        sa.Column("company_id", sa.String(length=100), nullable=False),
        sa.Column("namespace", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("extract_entity_types", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_file_id", sa.String(length=100), nullable=True),
        sa.Column("source_text_sha256", sa.String(length=64), nullable=True),
        sa.Column("split_by_headings", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("chunk_max_chars", sa.Integer(), nullable=False, server_default=sa.text("50000")),
        sa.Column("taskiq_task_id", sa.String(length=220), nullable=True),
        sa.Column("notes_created_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("entities_created_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("relationships_created_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_entity_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_relationship_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("attachment_document_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("chunk_errors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("import_id"),
    )
    op.create_index("ix_crm_knowledge_imports_company_id", "crm_knowledge_imports", ["company_id"])
    op.create_index("ix_crm_knowledge_imports_namespace", "crm_knowledge_imports", ["namespace"])
    op.create_index("ix_crm_knowledge_imports_status", "crm_knowledge_imports", ["status"])
    op.create_index(
        "ix_crm_knowledge_imports_company_ns_status",
        "crm_knowledge_imports",
        ["company_id", "namespace", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_crm_knowledge_imports_company_ns_status", table_name="crm_knowledge_imports")
    op.drop_index("ix_crm_knowledge_imports_status", table_name="crm_knowledge_imports")
    op.drop_index("ix_crm_knowledge_imports_namespace", table_name="crm_knowledge_imports")
    op.drop_index("ix_crm_knowledge_imports_company_id", table_name="crm_knowledge_imports")
    op.drop_table("crm_knowledge_imports")

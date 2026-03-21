"""Baseline crm DB

Revision ID: crm_0001
Revises:
Create Date: 2026-03-20
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "crm_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crm_entities",
        sa.Column("entity_id", sa.String(100), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("namespace", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_subtype", sa.String(100), nullable=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("attributes", postgresql.JSONB(), nullable=False),
        sa.Column("priority", sa.String(50), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("note_date", sa.Date(), nullable=True),
        sa.Column("assignees", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("attachment_ids", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("source_entity_id", sa.String(100), nullable=True),
        sa.Column("source_company_id", sa.String(100), nullable=True),
        sa.Column("relevance", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_crm_entities_company_id", "crm_entities", ["company_id"])
    op.create_index("ix_crm_entities_entity_type", "crm_entities", ["entity_type"])
    op.create_index("ix_crm_entities_company_type", "crm_entities", ["company_id", "entity_type"])
    op.create_index("ix_crm_entities_tags", "crm_entities", ["tags"], postgresql_using="gin")
    op.create_index("ix_crm_entities_due_date", "crm_entities", ["due_date"])
    op.create_index("ix_crm_entities_note_date", "crm_entities", ["note_date"])
    op.create_index("ix_crm_entities_namespace", "crm_entities", ["company_id", "namespace"])

    op.create_table(
        "entity_types",
        sa.Column("type_id", sa.String(100), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_type_id", sa.String(100), nullable=True),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("color", sa.String(20), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("fields_schema", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_entity_types_company_id", "entity_types", ["company_id"])

    op.create_table(
        "relationship_types",
        sa.Column("type_id", sa.String(100), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("is_directed", sa.Boolean(), nullable=False),
        sa.Column("inverse_type_id", sa.String(100), nullable=True),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("color", sa.String(20), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("weight_default", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("type_id", "company_id", name="uq_relationship_type_company"),
    )
    op.create_index("ix_relationship_types_company_id", "relationship_types", ["company_id"])
    op.create_index("idx_relationship_types_system", "relationship_types", ["is_system"])

    op.create_table(
        "relationships",
        sa.Column("relationship_id", sa.String(100), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("namespace", sa.String(100), nullable=False),
        sa.Column("source_entity_id", sa.String(100), nullable=False),
        sa.Column("target_entity_id", sa.String(100), nullable=False),
        sa.Column("relationship_type", sa.String(100), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("attributes", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_relationships_company_id", "relationships", ["company_id"])
    op.create_index("idx_relationships_source", "relationships", ["source_entity_id"])
    op.create_index("idx_relationships_target", "relationships", ["target_entity_id"])
    op.create_index("idx_relationships_source_target", "relationships", ["source_entity_id", "target_entity_id"])
    op.create_index("idx_relationships_type", "relationships", ["relationship_type"])
    op.create_index("idx_relationships_namespace", "relationships", ["company_id", "namespace"])

    op.create_table(
        "company_mapping",
        sa.Column("company_id", sa.String(100), primary_key=True, nullable=False),
        sa.Column("entity_id", sa.String(100), nullable=False),
        sa.Column("is_owner", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_company_mapping_entity_id", "company_mapping", ["entity_id"])

    op.create_table(
        "access_grants",
        sa.Column("grant_id", sa.String(100), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(200), nullable=False),
        sa.Column("grant_type", sa.String(50), nullable=False),
        sa.Column("target_user_id", sa.String(100), nullable=True),
        sa.Column("target_company_id", sa.String(100), nullable=True),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("access_token", sa.String(100), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_access_grants_company_id", "access_grants", ["company_id"])
    op.create_index("idx_grants_resource", "access_grants", ["resource_type", "resource_id", "company_id"])
    op.create_index("idx_grants_target_user", "access_grants", ["target_user_id"])
    op.create_index("idx_grants_target_company", "access_grants", ["target_company_id"])
    op.create_index("idx_grants_token", "access_grants", ["access_token"])

    op.create_table(
        "access_requests",
        sa.Column("request_id", sa.String(100), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("requester_id", sa.String(100), nullable=False),
        sa.Column("requester_company_id", sa.String(100), nullable=False),
        sa.Column("owner_id", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("include_dependencies", sa.Boolean(), nullable=False),
        sa.Column("max_depth", sa.Integer(), nullable=False),
        sa.Column("created_entity_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_access_requests_company_id", "access_requests", ["company_id"])
    op.create_index("ix_access_requests_requester_id", "access_requests", ["requester_id"])
    op.create_index("ix_access_requests_requester_company_id", "access_requests", ["requester_company_id"])
    op.create_index("ix_access_requests_owner_id", "access_requests", ["owner_id"])
    op.create_index("ix_access_requests_resource_id", "access_requests", ["resource_id"])


def downgrade() -> None:
    op.drop_table("access_requests")
    op.drop_table("access_grants")
    op.drop_table("company_mapping")
    op.drop_table("relationships")
    op.drop_table("relationship_types")
    op.drop_table("entity_types")
    op.drop_table("crm_entities")

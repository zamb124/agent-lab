"""Bindings PK -> file_id; drop binding_id everywhere; no legacy map table.

Revision ID: office_0013
Revises: office_0012
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "office_0013"
down_revision: Union[str, None] = "office_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- office_binding_members: add file_id, backfill from parent binding ---
    op.add_column(
        "office_binding_members",
        sa.Column("file_id", sa.String(length=128), nullable=True),
    )
    op.execute(
        """
        UPDATE office_binding_members m
        SET file_id = b.file_id
        FROM office_document_bindings b
        WHERE m.binding_id = b.binding_id
        """
    )
    op.alter_column("office_binding_members", "file_id", nullable=False)

    # --- office_document_shares: add file_id, backfill from parent binding ---
    op.add_column(
        "office_document_shares",
        sa.Column("file_id", sa.String(length=128), nullable=True),
    )
    op.execute(
        """
        UPDATE office_document_shares s
        SET file_id = b.file_id
        FROM office_document_bindings b
        WHERE s.binding_id = b.binding_id
        """
    )
    op.alter_column("office_document_shares", "file_id", nullable=False)

    # --- office_document_events: add file_id, backfill from parent binding ---
    op.add_column(
        "office_document_events",
        sa.Column("file_id", sa.String(length=128), nullable=True),
    )
    op.execute(
        """
        UPDATE office_document_events e
        SET file_id = b.file_id
        FROM office_document_bindings b
        WHERE e.binding_id = b.binding_id
        """
    )
    op.alter_column("office_document_events", "file_id", nullable=False)

    # --- office_document_revisions: split snapshot file_id from parent ref ---
    op.add_column(
        "office_document_revisions",
        sa.Column("revision_file_id", sa.String(length=128), nullable=True),
    )
    op.execute(
        """
        UPDATE office_document_revisions
        SET revision_file_id = file_id
        """
    )
    op.execute(
        """
        UPDATE office_document_revisions r
        SET file_id = b.file_id
        FROM office_document_bindings b
        WHERE r.binding_id = b.binding_id
        """
    )
    op.alter_column("office_document_revisions", "revision_file_id", nullable=False)

    # --- drop old binding_id FKs / indexes / columns on children ---
    op.drop_constraint(
        "office_binding_members_binding_id_fkey", "office_binding_members", type_="foreignkey"
    )
    op.drop_constraint("office_binding_members_pkey", "office_binding_members", type_="primary")
    op.drop_column("office_binding_members", "binding_id")
    op.create_primary_key("office_binding_members_pkey", "office_binding_members", ["file_id", "user_id"])

    op.drop_index(op.f("ix_office_document_shares_binding_id"), table_name="office_document_shares")
    op.drop_constraint(
        "office_document_shares_binding_id_fkey", "office_document_shares", type_="foreignkey"
    )
    op.drop_column("office_document_shares", "binding_id")

    op.drop_index(op.f("ix_office_document_events_binding_id"), table_name="office_document_events")
    op.drop_constraint(
        "office_document_events_binding_id_fkey", "office_document_events", type_="foreignkey"
    )
    op.drop_column("office_document_events", "binding_id")

    op.drop_index("ix_office_revisions_binding_number", table_name="office_document_revisions")
    op.drop_index(op.f("ix_office_document_revisions_binding_id"), table_name="office_document_revisions")
    op.drop_constraint(
        "office_document_revisions_binding_id_fkey", "office_document_revisions", type_="foreignkey"
    )
    op.drop_column("office_document_revisions", "binding_id")

    # --- office_document_bindings: PK binding_id -> file_id ---
    op.drop_index("uq_office_bindings_company_namespace_file", table_name="office_document_bindings")
    op.drop_constraint("office_document_bindings_pkey", "office_document_bindings", type_="primary")
    op.create_primary_key("office_document_bindings_pkey", "office_document_bindings", ["file_id"])
    op.drop_column("office_document_bindings", "binding_id")
    op.create_index(
        "uq_office_bindings_company_namespace_file",
        "office_document_bindings",
        ["company_id", "namespace", "file_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # --- add new FKs / indexes from children to bindings.file_id ---
    op.create_foreign_key(
        "fk_office_binding_members_file_id",
        "office_binding_members",
        "office_document_bindings",
        ["file_id"],
        ["file_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_office_document_shares_file_id",
        "office_document_shares",
        "office_document_bindings",
        ["file_id"],
        ["file_id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_office_document_shares_file_id"), "office_document_shares", ["file_id"]
    )
    op.create_foreign_key(
        "fk_office_document_events_file_id",
        "office_document_events",
        "office_document_bindings",
        ["file_id"],
        ["file_id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_office_document_events_file_id"), "office_document_events", ["file_id"]
    )
    op.create_foreign_key(
        "fk_office_document_revisions_file_id",
        "office_document_revisions",
        "office_document_bindings",
        ["file_id"],
        ["file_id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_office_document_revisions_file_id"), "office_document_revisions", ["file_id"]
    )
    op.create_index(
        "ix_office_revisions_file_number",
        "office_document_revisions",
        ["file_id", "revision_number"],
    )


def downgrade() -> None:
    # --- office_document_bindings: PK file_id -> binding_id (best effort, new synthetic ids) ---
    op.drop_index("ix_office_revisions_file_number", table_name="office_document_revisions")
    op.drop_index(op.f("ix_office_document_revisions_file_id"), table_name="office_document_revisions")
    op.drop_constraint(
        "fk_office_document_revisions_file_id", "office_document_revisions", type_="foreignkey"
    )
    op.drop_index(op.f("ix_office_document_events_file_id"), table_name="office_document_events")
    op.drop_constraint(
        "fk_office_document_events_file_id", "office_document_events", type_="foreignkey"
    )
    op.drop_index(op.f("ix_office_document_shares_file_id"), table_name="office_document_shares")
    op.drop_constraint(
        "fk_office_document_shares_file_id", "office_document_shares", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_office_binding_members_file_id", "office_binding_members", type_="foreignkey"
    )

    op.drop_index("uq_office_bindings_company_namespace_file", table_name="office_document_bindings")
    op.add_column(
        "office_document_bindings",
        sa.Column("binding_id", sa.String(length=64), nullable=True),
    )
    op.execute(
        """
        UPDATE office_document_bindings
        SET binding_id = md5(random()::text || clock_timestamp()::text)
        """
    )
    op.alter_column("office_document_bindings", "binding_id", nullable=False)
    op.drop_constraint("office_document_bindings_pkey", "office_document_bindings", type_="primary")
    op.create_primary_key("office_document_bindings_pkey", "office_document_bindings", ["binding_id"])
    op.create_index(
        "uq_office_bindings_company_namespace_file",
        "office_document_bindings",
        ["company_id", "namespace", "file_id"],
        unique=True,
    )

    # --- office_binding_members: file_id -> binding_id ---
    op.add_column(
        "office_binding_members",
        sa.Column("binding_id", sa.String(length=64), nullable=True),
    )
    op.execute(
        """
        UPDATE office_binding_members m
        SET binding_id = b.binding_id
        FROM office_document_bindings b
        WHERE m.file_id = b.file_id
        """
    )
    op.alter_column("office_binding_members", "binding_id", nullable=False)
    op.drop_constraint("office_binding_members_pkey", "office_binding_members", type_="primary")
    op.drop_column("office_binding_members", "file_id")
    op.create_primary_key("office_binding_members_pkey", "office_binding_members", ["binding_id", "user_id"])
    op.create_foreign_key(
        "office_binding_members_binding_id_fkey",
        "office_binding_members",
        "office_document_bindings",
        ["binding_id"],
        ["binding_id"],
        ondelete="CASCADE",
    )

    # --- office_document_shares: file_id -> binding_id ---
    op.add_column(
        "office_document_shares",
        sa.Column("binding_id", sa.String(length=64), nullable=True),
    )
    op.execute(
        """
        UPDATE office_document_shares s
        SET binding_id = b.binding_id
        FROM office_document_bindings b
        WHERE s.file_id = b.file_id
        """
    )
    op.alter_column("office_document_shares", "binding_id", nullable=False)
    op.drop_column("office_document_shares", "file_id")
    op.create_foreign_key(
        "office_document_shares_binding_id_fkey",
        "office_document_shares",
        "office_document_bindings",
        ["binding_id"],
        ["binding_id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_office_document_shares_binding_id"), "office_document_shares", ["binding_id"]
    )

    # --- office_document_events: file_id -> binding_id ---
    op.add_column(
        "office_document_events",
        sa.Column("binding_id", sa.String(length=64), nullable=True),
    )
    op.execute(
        """
        UPDATE office_document_events e
        SET binding_id = b.binding_id
        FROM office_document_bindings b
        WHERE e.file_id = b.file_id
        """
    )
    op.alter_column("office_document_events", "binding_id", nullable=False)
    op.drop_column("office_document_events", "file_id")
    op.create_foreign_key(
        "office_document_events_binding_id_fkey",
        "office_document_events",
        "office_document_bindings",
        ["binding_id"],
        ["binding_id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_office_document_events_binding_id"), "office_document_events", ["binding_id"]
    )

    # --- office_document_revisions: file_id -> binding_id, restore snapshot file_id ---
    op.add_column(
        "office_document_revisions",
        sa.Column("binding_id", sa.String(length=64), nullable=True),
    )
    op.execute(
        """
        UPDATE office_document_revisions r
        SET binding_id = b.binding_id
        FROM office_document_bindings b
        WHERE r.file_id = b.file_id
        """
    )
    op.alter_column("office_document_revisions", "binding_id", nullable=False)
    op.execute(
        """
        UPDATE office_document_revisions
        SET file_id = revision_file_id
        """
    )
    op.drop_column("office_document_revisions", "revision_file_id")
    op.create_foreign_key(
        "office_document_revisions_binding_id_fkey",
        "office_document_revisions",
        "office_document_bindings",
        ["binding_id"],
        ["binding_id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_office_document_revisions_binding_id"), "office_document_revisions", ["binding_id"]
    )
    op.create_index(
        "ix_office_revisions_binding_number", "office_document_revisions", ["binding_id", "revision_number"]
    )

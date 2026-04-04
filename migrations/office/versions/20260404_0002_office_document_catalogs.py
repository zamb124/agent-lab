"""office document catalogs and binding.catalog_id

Revision ID: office_0002
Revises: office_0001
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "office_0002"
down_revision: Union[str, None] = "office_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "office_document_catalogs",
        sa.Column("catalog_id", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=100), nullable=False),
        sa.Column("namespace", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("owner_user_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("catalog_id"),
    )
    op.create_index(
        "ix_office_catalogs_company_namespace",
        "office_document_catalogs",
        ["company_id", "namespace"],
        unique=False,
    )

    op.create_table(
        "office_catalog_members",
        sa.Column("catalog_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["catalog_id"],
            ["office_document_catalogs.catalog_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("catalog_id", "user_id"),
    )

    op.add_column(
        "office_document_bindings",
        sa.Column("catalog_id", sa.String(length=64), nullable=True),
    )

    conn = op.get_bind()
    pairs = conn.execute(
        sa.text(
            "SELECT DISTINCT company_id, namespace FROM office_document_bindings"
        )
    ).fetchall()
    now = datetime.now(timezone.utc)
    for company_id, namespace in pairs:
        row = conn.execute(
            sa.text(
                """
                SELECT created_by_user_id FROM office_document_bindings
                WHERE company_id = :c AND namespace = :n
                ORDER BY created_at ASC
                LIMIT 1
                """
            ),
            {"c": company_id, "n": namespace},
        ).fetchone()
        if row is None:
            continue
        owner_user_id = row[0]
        catalog_id = uuid.uuid4().hex
        conn.execute(
            sa.text(
                """
                INSERT INTO office_document_catalogs
                (catalog_id, company_id, namespace, title, owner_user_id, created_at)
                VALUES (:id, :c, :n, :t, :o, :at)
                """
            ),
            {
                "id": catalog_id,
                "c": company_id,
                "n": namespace,
                "t": "Общие",
                "o": owner_user_id,
                "at": now,
            },
        )
        conn.execute(
            sa.text(
                """
                UPDATE office_document_bindings
                SET catalog_id = :cid
                WHERE company_id = :c AND namespace = :n
                """
            ),
            {"cid": catalog_id, "c": company_id, "n": namespace},
        )

    op.create_foreign_key(
        "fk_office_bindings_catalog_id",
        "office_document_bindings",
        "office_document_catalogs",
        ["catalog_id"],
        ["catalog_id"],
        ondelete="CASCADE",
    )
    op.alter_column(
        "office_document_bindings",
        "catalog_id",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.create_index(
        "ix_office_bindings_catalog_id",
        "office_document_bindings",
        ["catalog_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_office_bindings_catalog_id", table_name="office_document_bindings")
    op.drop_constraint(
        "fk_office_bindings_catalog_id",
        "office_document_bindings",
        type_="foreignkey",
    )
    op.drop_column("office_document_bindings", "catalog_id")
    op.drop_table("office_catalog_members")
    op.drop_index("ix_office_catalogs_company_namespace", table_name="office_document_catalogs")
    op.drop_table("office_document_catalogs")

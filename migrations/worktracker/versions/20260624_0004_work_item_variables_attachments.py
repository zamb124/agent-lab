"""WorkItem variables, attachments; comment/resolution FileRef files

Revision ID: worktracker_0004
Revises: worktracker_0003
Create Date: 2026-06-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "worktracker_0004"
down_revision: Union[str, None] = "worktracker_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    item_columns = _table_columns("work_items")
    if "variables" not in item_columns:
        op.add_column(
            "work_items",
            sa.Column(
                "variables",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )
    if "attachments" not in item_columns:
        op.add_column(
            "work_items",
            sa.Column(
                "attachments",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )

    comment_columns = _table_columns("work_item_comments")
    if "files" not in comment_columns:
        op.add_column(
            "work_item_comments",
            sa.Column(
                "files",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )
    if "file_ids" in comment_columns:
        op.execute(
            """
            UPDATE work_item_comments
            SET files = COALESCE(
                (
                    SELECT jsonb_agg(
                        jsonb_build_object(
                            'file_id', fid,
                            'original_name', fid,
                            'content_type', 'application/octet-stream',
                            'file_size', 0
                        )
                    )
                    FROM jsonb_array_elements_text(file_ids) AS fid
                ),
                '[]'::jsonb
            )
            WHERE jsonb_array_length(COALESCE(file_ids, '[]'::jsonb)) > 0
            """
        )
        op.drop_column("work_item_comments", "file_ids")

    op.execute(
        """
        UPDATE work_items
        SET resolution = resolution
            - 'file_ids'
            || jsonb_build_object(
                'files',
                COALESCE(
                    (
                        SELECT jsonb_agg(
                            jsonb_build_object(
                                'file_id', fid,
                                'original_name', fid,
                                'content_type', 'application/octet-stream',
                                'file_size', 0
                            )
                        )
                        FROM jsonb_array_elements_text(resolution->'file_ids') AS fid
                    ),
                    '[]'::jsonb
                )
            )
        WHERE resolution IS NOT NULL
          AND resolution ? 'file_ids'
        """
    )


def downgrade() -> None:
    comment_columns = _table_columns("work_item_comments")
    if "file_ids" not in comment_columns and "files" in comment_columns:
        op.add_column(
            "work_item_comments",
            sa.Column(
                "file_ids",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )
        op.execute(
            """
            UPDATE work_item_comments
            SET file_ids = COALESCE(
                (
                    SELECT jsonb_agg(elem->>'file_id')
                    FROM jsonb_array_elements(files) AS elem
                    WHERE elem ? 'file_id'
                ),
                '[]'::jsonb
            )
            """
        )
        op.drop_column("work_item_comments", "files")

    item_columns = _table_columns("work_items")
    if "variables" in item_columns:
        op.drop_column("work_items", "variables")
    if "attachments" in item_columns:
        op.drop_column("work_items", "attachments")

    op.execute(
        """
        UPDATE work_items
        SET resolution = resolution
            - 'files'
            || jsonb_build_object(
                'file_ids',
                COALESCE(
                    (
                        SELECT jsonb_agg(elem->>'file_id')
                        FROM jsonb_array_elements(resolution->'files') AS elem
                        WHERE elem ? 'file_id'
                    ),
                    '[]'::jsonb
                )
            )
        WHERE resolution IS NOT NULL
          AND resolution ? 'files'
        """
    )

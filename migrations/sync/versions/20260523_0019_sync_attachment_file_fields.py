"""Нормализовать file-поля в sync_message_contents.data.

Revision ID: sync_0019
Revises: sync_0018
"""

from typing import Sequence, Union

from alembic import op

revision: str = "sync_0019"
down_revision: Union[str, None] = "sync_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FILE_CONTENT_TYPES = "('file/image', 'file/document', 'file/audio', 'file/video')"


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE sync_message_contents
        SET data =
            (data - 'filename' - 'mime_type' - 'size')
            || jsonb_strip_nulls(jsonb_build_object(
                'original_name', data->'filename',
                'content_type', data->'mime_type',
                'file_size', data->'size'
            ))
        WHERE type IN {FILE_CONTENT_TYPES}
          AND (
            data ? 'filename'
            OR data ? 'mime_type'
            OR data ? 'size'
          )
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE sync_message_contents
        SET data =
            (data - 'original_name' - 'content_type' - 'file_size')
            || jsonb_strip_nulls(jsonb_build_object(
                'filename', data->'original_name',
                'mime_type', data->'content_type',
                'size', data->'file_size'
            ))
        WHERE type IN {FILE_CONTENT_TYPES}
          AND (
            data ? 'original_name'
            OR data ? 'content_type'
            OR data ? 'file_size'
          )
        """
    )

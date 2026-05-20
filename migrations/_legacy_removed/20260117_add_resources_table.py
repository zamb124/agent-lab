"""add resources table

Revision ID: 9b4c6d8e0f2a
Revises: 8a3b5c7d9e1f
Create Date: 2026-01-17 12:00:00.000000+00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Идентификаторы ревизии, используются Alembic.
revision: str = '9b4c6d8e0f2a'
down_revision: Union[str, None] = '8a3b5c7d9e1f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('resources',
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expired_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('key'),
        sa.UniqueConstraint('key', name='uq_resources_key')
    )
    op.create_index('ix_resources_expired_at', 'resources', ['expired_at'], unique=False)
    op.create_index(op.f('ix_resources_key'), 'resources', ['key'], unique=False)
    op.create_index('ix_resources_key_prefix', 'resources', ['key'], unique=False)
    op.create_index('ix_resources_updated_at', 'resources', ['updated_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_resources_updated_at', table_name='resources')
    op.drop_index('ix_resources_key_prefix', table_name='resources')
    op.drop_index(op.f('ix_resources_key'), table_name='resources')
    op.drop_index('ix_resources_expired_at', table_name='resources')
    op.drop_table('resources')

"""add mcp_servers table

Revision ID: 8a3b5c7d9e1f
Revises: 552d78152e45
Create Date: 2026-01-14 23:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8a3b5c7d9e1f'
down_revision: Union[str, None] = '552d78152e45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Создаём таблицу mcp_servers для хранения конфигураций MCP серверов
    op.create_table('mcp_servers',
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expired_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('key'),
        sa.UniqueConstraint('key', name='uq_mcp_servers_key')
    )
    op.create_index('ix_mcp_servers_expired_at', 'mcp_servers', ['expired_at'], unique=False)
    op.create_index(op.f('ix_mcp_servers_key'), 'mcp_servers', ['key'], unique=False)
    op.create_index('ix_mcp_servers_key_prefix', 'mcp_servers', ['key'], unique=False)
    op.create_index('ix_mcp_servers_updated_at', 'mcp_servers', ['updated_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_mcp_servers_updated_at', table_name='mcp_servers')
    op.drop_index('ix_mcp_servers_key_prefix', table_name='mcp_servers')
    op.drop_index(op.f('ix_mcp_servers_key'), table_name='mcp_servers')
    op.drop_index('ix_mcp_servers_expired_at', table_name='mcp_servers')
    op.drop_table('mcp_servers')

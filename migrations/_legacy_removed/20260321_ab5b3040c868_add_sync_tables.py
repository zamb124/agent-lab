"""add sync tables

Revision ID: ab5b3040c868
Revises: a1b2c3d4e5f6
Create Date: 2026-03-21 00:12:21.379766+00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Идентификаторы ревизии, используются Alembic.
revision: str = 'ab5b3040c868'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### команды автоматически сгенерированы Alembic - при необходимости поправьте ###
    op.create_table('sync_files',
    sa.Column('file_id', sa.String(length=64), nullable=False),
    sa.Column('company_id', sa.String(length=100), nullable=False),
    sa.Column('original_name', sa.String(length=255), nullable=False),
    sa.Column('mime_type', sa.String(length=255), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('storage_url', sa.Text(), nullable=False),
    sa.Column('checksum', sa.String(length=128), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('file_id')
    )
    op.create_index('ix_sync_files_company', 'sync_files', ['company_id'], unique=False)
    op.create_index(op.f('ix_sync_files_company_id'), 'sync_files', ['company_id'], unique=False)
    op.create_table('sync_git_resource_refs',
    sa.Column('git_ref_id', sa.String(length=64), nullable=False),
    sa.Column('company_id', sa.String(length=100), nullable=False),
    sa.Column('provider', sa.String(length=32), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('project_key', sa.String(length=255), nullable=False),
    sa.Column('external_id', sa.String(length=255), nullable=False),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('extra', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.PrimaryKeyConstraint('git_ref_id')
    )
    op.create_index('ix_sync_git_refs_company', 'sync_git_resource_refs', ['company_id'], unique=False)
    op.create_index('ix_sync_git_refs_provider_kind', 'sync_git_resource_refs', ['provider', 'kind'], unique=False)
    op.create_index(op.f('ix_sync_git_resource_refs_company_id'), 'sync_git_resource_refs', ['company_id'], unique=False)
    op.create_table('sync_spaces',
    sa.Column('space_id', sa.String(length=64), nullable=False),
    sa.Column('company_id', sa.String(length=100), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_by_user_id', sa.String(length=64), nullable=False),
    sa.PrimaryKeyConstraint('space_id')
    )
    op.create_index('ix_sync_spaces_company', 'sync_spaces', ['company_id'], unique=False)
    op.create_index(op.f('ix_sync_spaces_company_id'), 'sync_spaces', ['company_id'], unique=False)
    op.create_table('sync_channels',
    sa.Column('channel_id', sa.String(length=64), nullable=False),
    sa.Column('company_id', sa.String(length=100), nullable=False),
    sa.Column('space_id', sa.String(length=64), nullable=True),
    sa.Column('type', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('is_private', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_by_user_id', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['space_id'], ['sync_spaces.space_id'], ),
    sa.PrimaryKeyConstraint('channel_id')
    )
    op.create_index('ix_sync_channels_company', 'sync_channels', ['company_id'], unique=False)
    op.create_index(op.f('ix_sync_channels_company_id'), 'sync_channels', ['company_id'], unique=False)
    op.create_index('ix_sync_channels_space', 'sync_channels', ['space_id'], unique=False)
    op.create_table('sync_channel_members',
    sa.Column('channel_id', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=False),
    sa.Column('company_id', sa.String(length=100), nullable=False),
    sa.Column('role', sa.String(length=32), nullable=False),
    sa.ForeignKeyConstraint(['channel_id'], ['sync_channels.channel_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('channel_id', 'user_id')
    )
    op.create_index('ix_sync_channel_members_company', 'sync_channel_members', ['company_id'], unique=False)
    op.create_table('sync_threads',
    sa.Column('thread_id', sa.String(length=64), nullable=False),
    sa.Column('company_id', sa.String(length=100), nullable=False),
    sa.Column('channel_id', sa.String(length=64), nullable=False),
    sa.Column('root_message_id', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_by_user_id', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['channel_id'], ['sync_channels.channel_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('thread_id')
    )
    op.create_index('ix_sync_threads_channel', 'sync_threads', ['channel_id'], unique=False)
    op.create_index('ix_sync_threads_company', 'sync_threads', ['company_id'], unique=False)
    op.create_index(op.f('ix_sync_threads_company_id'), 'sync_threads', ['company_id'], unique=False)
    op.create_table('sync_messages',
    sa.Column('message_id', sa.String(length=64), nullable=False),
    sa.Column('company_id', sa.String(length=100), nullable=False),
    sa.Column('channel_id', sa.String(length=64), nullable=False),
    sa.Column('thread_id', sa.String(length=64), nullable=True),
    sa.Column('parent_message_id', sa.String(length=64), nullable=True),
    sa.Column('sender_user_id', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('edited_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['channel_id'], ['sync_channels.channel_id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['parent_message_id'], ['sync_messages.message_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['thread_id'], ['sync_threads.thread_id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('message_id')
    )
    op.create_index('ix_sync_messages_channel', 'sync_messages', ['channel_id'], unique=False)
    op.create_index('ix_sync_messages_company', 'sync_messages', ['company_id'], unique=False)
    op.create_index(op.f('ix_sync_messages_company_id'), 'sync_messages', ['company_id'], unique=False)
    op.create_index('ix_sync_messages_sent_at', 'sync_messages', ['sent_at'], unique=False)
    op.create_index('ix_sync_messages_thread', 'sync_messages', ['thread_id'], unique=False)
    op.create_table('sync_message_contents',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('message_id', sa.String(length=64), nullable=False),
    sa.Column('type', sa.String(length=64), nullable=False),
    sa.Column('order', sa.Integer(), nullable=False),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.ForeignKeyConstraint(['message_id'], ['sync_messages.message_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_sync_message_contents_message', 'sync_message_contents', ['message_id'], unique=False)
    op.create_table('sync_message_files',
    sa.Column('message_id', sa.String(length=64), nullable=False),
    sa.Column('file_id', sa.String(length=64), nullable=False),
    sa.Column('role', sa.String(length=32), nullable=False),
    sa.ForeignKeyConstraint(['file_id'], ['sync_files.file_id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['message_id'], ['sync_messages.message_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('message_id', 'file_id')
    )


def downgrade() -> None:
    op.drop_table('sync_message_files')
    op.drop_index('ix_sync_message_contents_message', table_name='sync_message_contents')
    op.drop_table('sync_message_contents')
    op.drop_index('ix_sync_messages_thread', table_name='sync_messages')
    op.drop_index('ix_sync_messages_sent_at', table_name='sync_messages')
    op.drop_index(op.f('ix_sync_messages_company_id'), table_name='sync_messages')
    op.drop_index('ix_sync_messages_company', table_name='sync_messages')
    op.drop_index('ix_sync_messages_channel', table_name='sync_messages')
    op.drop_table('sync_messages')
    op.drop_index(op.f('ix_sync_threads_company_id'), table_name='sync_threads')
    op.drop_index('ix_sync_threads_company', table_name='sync_threads')
    op.drop_index('ix_sync_threads_channel', table_name='sync_threads')
    op.drop_table('sync_threads')
    op.drop_index('ix_sync_channel_members_company', table_name='sync_channel_members')
    op.drop_table('sync_channel_members')
    op.drop_index('ix_sync_channels_space', table_name='sync_channels')
    op.drop_index(op.f('ix_sync_channels_company_id'), table_name='sync_channels')
    op.drop_index('ix_sync_channels_company', table_name='sync_channels')
    op.drop_table('sync_channels')
    op.drop_index(op.f('ix_sync_spaces_company_id'), table_name='sync_spaces')
    op.drop_index('ix_sync_spaces_company', table_name='sync_spaces')
    op.drop_table('sync_spaces')
    op.drop_index(op.f('ix_sync_git_resource_refs_company_id'), table_name='sync_git_resource_refs')
    op.drop_index('ix_sync_git_refs_provider_kind', table_name='sync_git_resource_refs')
    op.drop_index('ix_sync_git_refs_company', table_name='sync_git_resource_refs')
    op.drop_table('sync_git_resource_refs')
    op.drop_index(op.f('ix_sync_files_company_id'), table_name='sync_files')
    op.drop_index('ix_sync_files_company', table_name='sync_files')
    op.drop_table('sync_files')
    op.drop_index('ix_sync_message_contents_message', table_name='sync_message_contents')
    op.drop_table('sync_message_contents')
    op.drop_index('ix_sync_messages_thread', table_name='sync_messages')
    op.drop_index('ix_sync_messages_sent_at', table_name='sync_messages')
    op.drop_index(op.f('ix_sync_messages_company_id'), table_name='sync_messages')
    op.drop_index('ix_sync_messages_company', table_name='sync_messages')
    op.drop_index('ix_sync_messages_channel', table_name='sync_messages')
    op.drop_table('sync_messages')
    op.drop_index(op.f('ix_sync_threads_company_id'), table_name='sync_threads')
    op.drop_index('ix_sync_threads_company', table_name='sync_threads')
    op.drop_index('ix_sync_threads_channel', table_name='sync_threads')
    op.drop_table('sync_threads')
    op.drop_index('ix_sync_channel_members_company', table_name='sync_channel_members')
    op.drop_table('sync_channel_members')
    op.drop_index('ix_sync_channels_space', table_name='sync_channels')
    op.drop_index(op.f('ix_sync_channels_company_id'), table_name='sync_channels')
    op.drop_index('ix_sync_channels_company', table_name='sync_channels')
    op.drop_table('sync_channels')
    op.drop_index(op.f('ix_sync_spaces_company_id'), table_name='sync_spaces')
    op.drop_index('ix_sync_spaces_company', table_name='sync_spaces')
    op.drop_table('sync_spaces')
    op.drop_index(op.f('ix_sync_git_resource_refs_company_id'), table_name='sync_git_resource_refs')
    op.drop_index('ix_sync_git_refs_provider_kind', table_name='sync_git_resource_refs')
    op.drop_index('ix_sync_git_refs_company', table_name='sync_git_resource_refs')
    op.drop_table('sync_git_resource_refs')
    op.drop_index(op.f('ix_sync_files_company_id'), table_name='sync_files')
    op.drop_index('ix_sync_files_company', table_name='sync_files')
    op.drop_table('sync_files')
    # ### end Alembic commands ###

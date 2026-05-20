"""initial

Revision ID: 552d78152e45
Revises:
Create Date: 2026-01-11 20:52:35.293473+00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Идентификаторы ревизии, используются Alembic.
revision: str = '552d78152e45'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### команды автоматически сгенерированы Alembic - при необходимости поправьте ###
    op.create_table('access_grants',
    sa.Column('grant_id', sa.String(length=100), nullable=False),
    sa.Column('company_id', sa.String(length=100), nullable=False),
    sa.Column('created_by', sa.String(length=100), nullable=False),
    sa.Column('resource_type', sa.String(length=50), nullable=False, comment='entity | namespace'),
    sa.Column('resource_id', sa.String(length=200), nullable=False, comment='entity_id или namespace name'),
    sa.Column('grant_type', sa.String(length=50), nullable=False, comment='public | user | company'),
    sa.Column('target_user_id', sa.String(length=100), nullable=True, comment='User ID (может быть из любой компании)'),
    sa.Column('target_company_id', sa.String(length=100), nullable=True, comment='Company ID'),
    sa.Column('role', sa.String(length=50), nullable=False, comment='viewer | editor | admin'),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True, comment='Срок действия (опционально)'),
    sa.Column('access_token', sa.String(length=100), nullable=True, comment='Токен для шаринга по ссылке'),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('grant_id'),
    sa.UniqueConstraint('access_token')
    )
    op.create_index('idx_grants_resource', 'access_grants', ['resource_type', 'resource_id', 'company_id'], unique=False)
    op.create_index('idx_grants_target_company', 'access_grants', ['target_company_id'], unique=False)
    op.create_index('idx_grants_target_user', 'access_grants', ['target_user_id'], unique=False)
    op.create_index('idx_grants_token', 'access_grants', ['access_token'], unique=False)
    op.create_index(op.f('ix_access_grants_company_id'), 'access_grants', ['company_id'], unique=False)
    op.create_index(op.f('ix_access_grants_resource_id'), 'access_grants', ['resource_id'], unique=False)
    op.create_index(op.f('ix_access_grants_target_company_id'), 'access_grants', ['target_company_id'], unique=False)
    op.create_index(op.f('ix_access_grants_target_user_id'), 'access_grants', ['target_user_id'], unique=False)
    op.create_table('access_requests',
    sa.Column('request_id', sa.String(length=100), nullable=False),
    sa.Column('company_id', sa.String(length=100), nullable=False),
    sa.Column('requester_id', sa.String(length=100), nullable=False),
    sa.Column('requester_company_id', sa.String(length=100), nullable=False),
    sa.Column('owner_id', sa.String(length=100), nullable=False),
    sa.Column('resource_type', sa.String(length=50), nullable=False),
    sa.Column('resource_id', sa.String(length=100), nullable=False),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('include_dependencies', sa.Boolean(), nullable=False),
    sa.Column('max_depth', sa.Integer(), nullable=False),
    sa.Column('created_entity_id', sa.String(length=100), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('request_id')
    )
    op.create_index('idx_access_requests_owner_status', 'access_requests', ['owner_id', 'status'], unique=False)
    op.create_index('idx_access_requests_resource', 'access_requests', ['resource_type', 'resource_id'], unique=False)
    op.create_index(op.f('ix_access_requests_company_id'), 'access_requests', ['company_id'], unique=False)
    op.create_index(op.f('ix_access_requests_owner_id'), 'access_requests', ['owner_id'], unique=False)
    op.create_index(op.f('ix_access_requests_requester_company_id'), 'access_requests', ['requester_company_id'], unique=False)
    op.create_index(op.f('ix_access_requests_requester_id'), 'access_requests', ['requester_id'], unique=False)
    op.create_index(op.f('ix_access_requests_resource_id'), 'access_requests', ['resource_id'], unique=False)
    op.create_table('agent_states',
    sa.Column('session_id', sa.String(length=255), nullable=False),
    sa.Column('store_id', sa.String(length=255), nullable=False),
    sa.Column('state_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('session_id')
    )
    op.create_index(op.f('ix_agent_states_session_id'), 'agent_states', ['session_id'], unique=False)
    op.create_index('ix_agent_states_store_id', 'agent_states', ['store_id'], unique=False)
    op.create_index('ix_agent_states_updated_at', 'agent_states', ['updated_at'], unique=False)
    op.create_table('agents',
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expired_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('key'),
    sa.UniqueConstraint('key', name='uq_agents_key')
    )
    op.create_index('ix_agents_expired_at', 'agents', ['expired_at'], unique=False)
    op.create_index(op.f('ix_agents_key'), 'agents', ['key'], unique=False)
    op.create_index('ix_agents_key_prefix', 'agents', ['key'], unique=False)
    op.create_index('ix_agents_updated_at', 'agents', ['updated_at'], unique=False)
    op.create_table('agents_versions',
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expired_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('key'),
    sa.UniqueConstraint('key', name='uq_agents_versions_key')
    )
    op.create_index('ix_agents_versions_expired_at', 'agents_versions', ['expired_at'], unique=False)
    op.create_index(op.f('ix_agents_versions_key'), 'agents_versions', ['key'], unique=False)
    op.create_index('ix_agents_versions_key_prefix', 'agents_versions', ['key'], unique=False)
    op.create_index('ix_agents_versions_updated_at', 'agents_versions', ['updated_at'], unique=False)
    op.create_table('company_mapping',
    sa.Column('company_id', sa.String(length=100), nullable=False),
    sa.Column('entity_id', sa.String(length=100), nullable=False),
    sa.Column('is_owner', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('company_id')
    )
    op.create_index(op.f('ix_company_mapping_entity_id'), 'company_mapping', ['entity_id'], unique=False)
    op.create_table('document_processing_status',
    sa.Column('document_id', sa.String(length=255), nullable=False),
    sa.Column('task_id', sa.String(length=255), nullable=False),
    sa.Column('namespace_id', sa.String(length=255), nullable=False),
    sa.Column('document_name', sa.String(length=500), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('error_message', sa.String(), nullable=True),
    sa.Column('s3_key', sa.String(length=1000), nullable=True),
    sa.Column('s3_bucket', sa.String(length=255), nullable=True),
    sa.Column('file_size', sa.Integer(), nullable=True),
    sa.Column('chunks_count', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('extra_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.PrimaryKeyConstraint('document_id')
    )
    op.create_index(op.f('ix_document_processing_status_document_id'), 'document_processing_status', ['document_id'], unique=False)
    op.create_index(op.f('ix_document_processing_status_namespace_id'), 'document_processing_status', ['namespace_id'], unique=False)
    op.create_index(op.f('ix_document_processing_status_status'), 'document_processing_status', ['status'], unique=False)
    op.create_index(op.f('ix_document_processing_status_task_id'), 'document_processing_status', ['task_id'], unique=True)
    op.create_index('ix_document_status_namespace_status', 'document_processing_status', ['namespace_id', 'status'], unique=False)
    op.create_index('ix_document_status_task_id', 'document_processing_status', ['task_id'], unique=False)
    op.create_table('entity_types',
    sa.Column('type_id', sa.String(length=100), nullable=False),
    sa.Column('company_id', sa.String(length=100), nullable=False),
    sa.Column('parent_type_id', sa.String(length=100), nullable=True),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('prompt', sa.Text(), nullable=True, comment='Промпт для AI извлечения этого типа'),
    sa.Column('required_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('optional_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('icon', sa.String(length=50), nullable=True),
    sa.Column('color', sa.String(length=20), nullable=True),
    sa.Column('is_system', sa.Boolean(), nullable=False, comment='Создан из системного шаблона (но с company_id!)'),
    sa.Column('is_event', sa.Boolean(), nullable=False),
    sa.Column('check_duplicates', sa.Boolean(), nullable=False),
    sa.Column('weight_coefficient', sa.Float(), nullable=False),
    sa.Column('public_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='Какие поля показывать при публичном доступе'),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['parent_type_id'], ['entity_types.type_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('type_id'),
    sa.UniqueConstraint('type_id', 'company_id', name='uq_entity_type_company')
    )
    op.create_index('idx_entity_types_parent', 'entity_types', ['parent_type_id'], unique=False)
    op.create_index('idx_entity_types_system', 'entity_types', ['is_system'], unique=False)
    op.create_index(op.f('ix_entity_types_company_id'), 'entity_types', ['company_id'], unique=False)
    op.create_index(op.f('ix_entity_types_parent_type_id'), 'entity_types', ['parent_type_id'], unique=False)
    op.create_table('evaluation_results',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('agent_id', sa.String(), nullable=False),
    sa.Column('skill_id', sa.String(), nullable=False),
    sa.Column('run_date', sa.Date(), nullable=False),
    sa.Column('iteration', sa.Integer(), nullable=False),
    sa.Column('test_case_id', sa.String(), nullable=False),
    sa.Column('task_id', sa.String(), nullable=True),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('duration_ms', sa.Integer(), nullable=False),
    sa.Column('turns_count', sa.Integer(), nullable=False),
    sa.Column('dialog', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('scores', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('judge_feedback', sa.String(), nullable=True),
    sa.Column('error', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('agent_id', 'skill_id', 'run_date', 'iteration', 'test_case_id', name='uq_evaluation_results')
    )
    op.create_index('ix_evaluation_results_agent_skill', 'evaluation_results', ['agent_id', 'skill_id'], unique=False)
    op.create_table('namespaces',
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('expired_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('key'),
    sa.UniqueConstraint('key', name='uq_namespaces_key')
    )
    op.create_index('ix_namespaces_company_id', 'namespaces', [sa.literal_column("(value->>'company_id')")], unique=False)
    op.create_index(op.f('ix_namespaces_key'), 'namespaces', ['key'], unique=False)
    op.create_index('ix_namespaces_key_prefix', 'namespaces', ['key'], unique=False)
    op.create_table('nodes',
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expired_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('key'),
    sa.UniqueConstraint('key', name='uq_nodes_key')
    )
    op.create_index('ix_nodes_expired_at', 'nodes', ['expired_at'], unique=False)
    op.create_index(op.f('ix_nodes_key'), 'nodes', ['key'], unique=False)
    op.create_index('ix_nodes_key_prefix', 'nodes', ['key'], unique=False)
    op.create_index('ix_nodes_updated_at', 'nodes', ['updated_at'], unique=False)
    op.create_table('push_subscriptions',
    sa.Column('id', sa.String(length=255), nullable=False),
    sa.Column('user_id', sa.String(length=255), nullable=False),
    sa.Column('endpoint', sa.String(length=2048), nullable=False),
    sa.Column('keys', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('user_agent', sa.String(length=512), nullable=True),
    sa.Column('platform', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('endpoint')
    )
    op.create_index(op.f('ix_push_subscriptions_id'), 'push_subscriptions', ['id'], unique=False)
    op.create_index('ix_push_subscriptions_user_endpoint', 'push_subscriptions', ['user_id', 'endpoint'], unique=False)
    op.create_index(op.f('ix_push_subscriptions_user_id'), 'push_subscriptions', ['user_id'], unique=False)
    op.create_table('relationship_types',
    sa.Column('type_id', sa.String(length=100), nullable=False),
    sa.Column('company_id', sa.String(length=100), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('prompt', sa.Text(), nullable=True, comment='Промпт для AI извлечения этой связи'),
    sa.Column('is_directed', sa.Boolean(), nullable=False, comment='Направленная (A→B) или симметричная (A↔B)'),
    sa.Column('inverse_type_id', sa.String(length=100), nullable=True, comment='ID обратной связи (manages ↔ reports_to)'),
    sa.Column('icon', sa.String(length=50), nullable=True),
    sa.Column('color', sa.String(length=20), nullable=True),
    sa.Column('is_system', sa.Boolean(), nullable=False, comment='Создан из системного шаблона'),
    sa.Column('weight_default', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('type_id'),
    sa.UniqueConstraint('type_id', 'company_id', name='uq_relationship_type_company')
    )
    op.create_index('idx_relationship_types_system', 'relationship_types', ['is_system'], unique=False)
    op.create_index(op.f('ix_relationship_types_company_id'), 'relationship_types', ['company_id'], unique=False)
    op.create_table('relationships',
    sa.Column('relationship_id', sa.String(length=100), nullable=False),
    sa.Column('company_id', sa.String(length=100), nullable=False),
    sa.Column('namespace', sa.String(length=100), nullable=False),
    sa.Column('source_entity_id', sa.String(length=100), nullable=False),
    sa.Column('target_entity_id', sa.String(length=100), nullable=False),
    sa.Column('relationship_type', sa.String(length=100), nullable=False),
    sa.Column('weight', sa.Float(), nullable=False),
    sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('relationship_id')
    )
    op.create_index('idx_relationships_namespace', 'relationships', ['company_id', 'namespace'], unique=False)
    op.create_index('idx_relationships_source', 'relationships', ['source_entity_id'], unique=False)
    op.create_index('idx_relationships_source_target', 'relationships', ['source_entity_id', 'target_entity_id'], unique=False)
    op.create_index('idx_relationships_target', 'relationships', ['target_entity_id'], unique=False)
    op.create_index('idx_relationships_type', 'relationships', ['relationship_type'], unique=False)
    op.create_index(op.f('ix_relationships_company_id'), 'relationships', ['company_id'], unique=False)
    op.create_index(op.f('ix_relationships_namespace'), 'relationships', ['namespace'], unique=False)
    op.create_index(op.f('ix_relationships_relationship_type'), 'relationships', ['relationship_type'], unique=False)
    op.create_index(op.f('ix_relationships_source_entity_id'), 'relationships', ['source_entity_id'], unique=False)
    op.create_index(op.f('ix_relationships_target_entity_id'), 'relationships', ['target_entity_id'], unique=False)
    op.create_table('scheduled_tasks',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('schedule_id', sa.String(), nullable=True),
    sa.Column('agent_id', sa.String(), nullable=False),
    sa.Column('session_id', sa.String(), nullable=False),
    sa.Column('user_id', sa.String(), nullable=False),
    sa.Column('schedule_type', sa.String(), nullable=False),
    sa.Column('content_type', sa.String(), nullable=False),
    sa.Column('cron', sa.String(), nullable=True),
    sa.Column('interval_minutes', sa.Integer(), nullable=True),
    sa.Column('run_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('content', sa.String(), nullable=False),
    sa.Column('tool_args', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('next_run', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error_message', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_scheduled_tasks_agent_id', 'scheduled_tasks', ['agent_id'], unique=False)
    op.create_index('ix_scheduled_tasks_next_run', 'scheduled_tasks', ['next_run'], unique=False)
    op.create_index('ix_scheduled_tasks_session_id', 'scheduled_tasks', ['session_id'], unique=False)
    op.create_index('ix_scheduled_tasks_status', 'scheduled_tasks', ['status'], unique=False)
    op.create_table('spans',
    sa.Column('span_id', sa.String(), nullable=False),
    sa.Column('trace_id', sa.String(), nullable=False),
    sa.Column('parent_span_id', sa.String(), nullable=True),
    sa.Column('operation_name', sa.String(), nullable=False),
    sa.Column('kind', sa.String(), nullable=True),
    sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('status_message', sa.String(), nullable=True),
    sa.Column('user_id', sa.String(), nullable=True),
    sa.Column('user_name', sa.String(), nullable=True),
    sa.Column('user_groups', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('session_auth', sa.String(), nullable=True),
    sa.Column('session_agent', sa.String(), nullable=True),
    sa.Column('agent_id', sa.String(), nullable=True),
    sa.Column('task_id', sa.String(), nullable=True),
    sa.Column('context_id', sa.String(), nullable=True),
    sa.Column('skill_id', sa.String(), nullable=True),
    sa.Column('channel', sa.String(), nullable=True),
    sa.Column('node_id', sa.String(), nullable=True),
    sa.Column('agent_name', sa.String(), nullable=True),
    sa.Column('is_resume', sa.Boolean(), nullable=True),
    sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('events', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.PrimaryKeyConstraint('span_id')
    )
    op.create_index(op.f('ix_spans_agent_id'), 'spans', ['agent_id'], unique=False)
    op.create_index(op.f('ix_spans_context_id'), 'spans', ['context_id'], unique=False)
    op.create_index(op.f('ix_spans_parent_span_id'), 'spans', ['parent_span_id'], unique=False)
    op.create_index(op.f('ix_spans_session_agent'), 'spans', ['session_agent'], unique=False)
    op.create_index(op.f('ix_spans_session_auth'), 'spans', ['session_auth'], unique=False)
    op.create_index(op.f('ix_spans_span_id'), 'spans', ['span_id'], unique=False)
    op.create_index(op.f('ix_spans_start_time'), 'spans', ['start_time'], unique=False)
    op.create_index(op.f('ix_spans_task_id'), 'spans', ['task_id'], unique=False)
    op.create_index(op.f('ix_spans_trace_id'), 'spans', ['trace_id'], unique=False)
    op.create_index(op.f('ix_spans_user_id'), 'spans', ['user_id'], unique=False)
    op.create_table('states',
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expired_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('key'),
    sa.UniqueConstraint('key', name='uq_states_key')
    )
    op.create_index('ix_states_expired_at', 'states', ['expired_at'], unique=False)
    op.create_index(op.f('ix_states_key'), 'states', ['key'], unique=False)
    op.create_index('ix_states_key_prefix', 'states', ['key'], unique=False)
    op.create_index('ix_states_updated_at', 'states', ['updated_at'], unique=False)
    op.create_table('storage',
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expired_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('key'),
    sa.UniqueConstraint('key', name='uq_storage_key')
    )
    op.create_index('ix_storage_expired_at', 'storage', ['expired_at'], unique=False)
    op.create_index(op.f('ix_storage_key'), 'storage', ['key'], unique=False)
    op.create_index('ix_storage_key_created_at', 'storage', ['key', 'created_at'], unique=False)
    op.create_index('ix_storage_key_expired_at', 'storage', ['key', 'expired_at'], unique=False)
    op.create_index('ix_storage_key_prefix', 'storage', ['key'], unique=False)
    op.create_index('ix_storage_key_updated_at', 'storage', ['key', 'updated_at'], unique=False)
    op.create_index('ix_storage_updated_at', 'storage', ['updated_at'], unique=False)
    op.create_table('stores',
    sa.Column('store_id', sa.String(length=255), nullable=False),
    sa.Column('store_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('store_id')
    )
    op.create_index(op.f('ix_stores_store_id'), 'stores', ['store_id'], unique=False)
    op.create_index('ix_stores_updated_at', 'stores', ['updated_at'], unique=False)
    op.create_table('tools',
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expired_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('key'),
    sa.UniqueConstraint('key', name='uq_tools_key')
    )
    op.create_index('ix_tools_expired_at', 'tools', ['expired_at'], unique=False)
    op.create_index(op.f('ix_tools_key'), 'tools', ['key'], unique=False)
    op.create_index('ix_tools_key_prefix', 'tools', ['key'], unique=False)
    op.create_index('ix_tools_updated_at', 'tools', ['updated_at'], unique=False)
    op.create_table('usage',
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expired_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('key'),
    sa.UniqueConstraint('key', name='uq_usage_key')
    )
    op.create_index('ix_usage_company_id', 'usage', [sa.literal_column("(value->>'company_id')")], unique=False)
    op.create_index('ix_usage_expired_at', 'usage', ['expired_at'], unique=False)
    op.create_index(op.f('ix_usage_key'), 'usage', ['key'], unique=False)
    op.create_index('ix_usage_key_prefix', 'usage', ['key'], unique=False)
    op.create_index('ix_usage_resource_name', 'usage', [sa.literal_column("(value->>'resource_name')")], unique=False)
    op.create_index('ix_usage_timestamp', 'usage', [sa.literal_column("(value->>'timestamp')")], unique=False)
    op.create_index('ix_usage_updated_at', 'usage', ['updated_at'], unique=False)
    op.create_index('ix_usage_user_id', 'usage', [sa.literal_column("(value->>'user_id')")], unique=False)
    op.create_table('users',
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expired_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('key'),
    sa.UniqueConstraint('key', name='uq_users_key')
    )
    op.create_index('ix_users_expired_at', 'users', ['expired_at'], unique=False)
    op.create_index(op.f('ix_users_key'), 'users', ['key'], unique=False)
    op.create_index('ix_users_key_created_at', 'users', ['key', 'created_at'], unique=False)
    op.create_index('ix_users_key_expired_at', 'users', ['key', 'expired_at'], unique=False)
    op.create_index('ix_users_key_prefix', 'users', ['key'], unique=False)
    op.create_index('ix_users_key_updated_at', 'users', ['key', 'updated_at'], unique=False)
    op.create_index('ix_users_providers_jsonb', 'users', [sa.literal_column('value jsonb_path_ops')], unique=False, postgresql_using='gin', postgresql_where=sa.text("key LIKE 'user_providers:%'"))
    op.create_index('ix_users_updated_at', 'users', ['updated_at'], unique=False)
    op.create_table('variables',
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expired_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('key'),
    sa.UniqueConstraint('key', name='uq_variables_key')
    )
    op.create_index('ix_variables_expired_at', 'variables', ['expired_at'], unique=False)
    op.create_index(op.f('ix_variables_key'), 'variables', ['key'], unique=False)
    op.create_index('ix_variables_key_prefix', 'variables', ['key'], unique=False)
    op.create_index('ix_variables_updated_at', 'variables', ['updated_at'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### команды автоматически сгенерированы Alembic - при необходимости поправьте ###
    op.drop_index('ix_variables_updated_at', table_name='variables')
    op.drop_index('ix_variables_key_prefix', table_name='variables')
    op.drop_index(op.f('ix_variables_key'), table_name='variables')
    op.drop_index('ix_variables_expired_at', table_name='variables')
    op.drop_table('variables')
    op.drop_index('ix_users_updated_at', table_name='users')
    op.drop_index('ix_users_providers_jsonb', table_name='users', postgresql_using='gin', postgresql_where=sa.text("key LIKE 'user_providers:%'"))
    op.drop_index('ix_users_key_updated_at', table_name='users')
    op.drop_index('ix_users_key_prefix', table_name='users')
    op.drop_index('ix_users_key_expired_at', table_name='users')
    op.drop_index('ix_users_key_created_at', table_name='users')
    op.drop_index(op.f('ix_users_key'), table_name='users')
    op.drop_index('ix_users_expired_at', table_name='users')
    op.drop_table('users')
    op.drop_index('ix_usage_user_id', table_name='usage')
    op.drop_index('ix_usage_updated_at', table_name='usage')
    op.drop_index('ix_usage_timestamp', table_name='usage')
    op.drop_index('ix_usage_resource_name', table_name='usage')
    op.drop_index('ix_usage_key_prefix', table_name='usage')
    op.drop_index(op.f('ix_usage_key'), table_name='usage')
    op.drop_index('ix_usage_expired_at', table_name='usage')
    op.drop_index('ix_usage_company_id', table_name='usage')
    op.drop_table('usage')
    op.drop_index('ix_tools_updated_at', table_name='tools')
    op.drop_index('ix_tools_key_prefix', table_name='tools')
    op.drop_index(op.f('ix_tools_key'), table_name='tools')
    op.drop_index('ix_tools_expired_at', table_name='tools')
    op.drop_table('tools')
    op.drop_index('ix_stores_updated_at', table_name='stores')
    op.drop_index(op.f('ix_stores_store_id'), table_name='stores')
    op.drop_table('stores')
    op.drop_index('ix_storage_updated_at', table_name='storage')
    op.drop_index('ix_storage_key_updated_at', table_name='storage')
    op.drop_index('ix_storage_key_prefix', table_name='storage')
    op.drop_index('ix_storage_key_expired_at', table_name='storage')
    op.drop_index('ix_storage_key_created_at', table_name='storage')
    op.drop_index(op.f('ix_storage_key'), table_name='storage')
    op.drop_index('ix_storage_expired_at', table_name='storage')
    op.drop_table('storage')
    op.drop_index('ix_states_updated_at', table_name='states')
    op.drop_index('ix_states_key_prefix', table_name='states')
    op.drop_index(op.f('ix_states_key'), table_name='states')
    op.drop_index('ix_states_expired_at', table_name='states')
    op.drop_table('states')
    op.drop_index(op.f('ix_spans_user_id'), table_name='spans')
    op.drop_index(op.f('ix_spans_trace_id'), table_name='spans')
    op.drop_index(op.f('ix_spans_task_id'), table_name='spans')
    op.drop_index(op.f('ix_spans_start_time'), table_name='spans')
    op.drop_index(op.f('ix_spans_span_id'), table_name='spans')
    op.drop_index(op.f('ix_spans_session_auth'), table_name='spans')
    op.drop_index(op.f('ix_spans_session_agent'), table_name='spans')
    op.drop_index(op.f('ix_spans_parent_span_id'), table_name='spans')
    op.drop_index(op.f('ix_spans_context_id'), table_name='spans')
    op.drop_index(op.f('ix_spans_agent_id'), table_name='spans')
    op.drop_table('spans')
    op.drop_index('ix_scheduled_tasks_status', table_name='scheduled_tasks')
    op.drop_index('ix_scheduled_tasks_session_id', table_name='scheduled_tasks')
    op.drop_index('ix_scheduled_tasks_next_run', table_name='scheduled_tasks')
    op.drop_index('ix_scheduled_tasks_agent_id', table_name='scheduled_tasks')
    op.drop_table('scheduled_tasks')
    op.drop_index(op.f('ix_relationships_target_entity_id'), table_name='relationships')
    op.drop_index(op.f('ix_relationships_source_entity_id'), table_name='relationships')
    op.drop_index(op.f('ix_relationships_relationship_type'), table_name='relationships')
    op.drop_index(op.f('ix_relationships_namespace'), table_name='relationships')
    op.drop_index(op.f('ix_relationships_company_id'), table_name='relationships')
    op.drop_index('idx_relationships_type', table_name='relationships')
    op.drop_index('idx_relationships_target', table_name='relationships')
    op.drop_index('idx_relationships_source_target', table_name='relationships')
    op.drop_index('idx_relationships_source', table_name='relationships')
    op.drop_index('idx_relationships_namespace', table_name='relationships')
    op.drop_table('relationships')
    op.drop_index(op.f('ix_relationship_types_company_id'), table_name='relationship_types')
    op.drop_index('idx_relationship_types_system', table_name='relationship_types')
    op.drop_table('relationship_types')
    op.drop_index(op.f('ix_push_subscriptions_user_id'), table_name='push_subscriptions')
    op.drop_index('ix_push_subscriptions_user_endpoint', table_name='push_subscriptions')
    op.drop_index(op.f('ix_push_subscriptions_id'), table_name='push_subscriptions')
    op.drop_table('push_subscriptions')
    op.drop_index('ix_nodes_updated_at', table_name='nodes')
    op.drop_index('ix_nodes_key_prefix', table_name='nodes')
    op.drop_index(op.f('ix_nodes_key'), table_name='nodes')
    op.drop_index('ix_nodes_expired_at', table_name='nodes')
    op.drop_table('nodes')
    op.drop_index('ix_namespaces_key_prefix', table_name='namespaces')
    op.drop_index(op.f('ix_namespaces_key'), table_name='namespaces')
    op.drop_index('ix_namespaces_company_id', table_name='namespaces')
    op.drop_table('namespaces')
    op.drop_index('ix_evaluation_results_agent_skill', table_name='evaluation_results')
    op.drop_table('evaluation_results')
    op.drop_index(op.f('ix_entity_types_parent_type_id'), table_name='entity_types')
    op.drop_index(op.f('ix_entity_types_company_id'), table_name='entity_types')
    op.drop_index('idx_entity_types_system', table_name='entity_types')
    op.drop_index('idx_entity_types_parent', table_name='entity_types')
    op.drop_table('entity_types')
    op.drop_index('ix_document_status_task_id', table_name='document_processing_status')
    op.drop_index('ix_document_status_namespace_status', table_name='document_processing_status')
    op.drop_index(op.f('ix_document_processing_status_task_id'), table_name='document_processing_status')
    op.drop_index(op.f('ix_document_processing_status_status'), table_name='document_processing_status')
    op.drop_index(op.f('ix_document_processing_status_namespace_id'), table_name='document_processing_status')
    op.drop_index(op.f('ix_document_processing_status_document_id'), table_name='document_processing_status')
    op.drop_table('document_processing_status')
    op.drop_index(op.f('ix_company_mapping_entity_id'), table_name='company_mapping')
    op.drop_table('company_mapping')
    op.drop_index('ix_agents_versions_updated_at', table_name='agents_versions')
    op.drop_index('ix_agents_versions_key_prefix', table_name='agents_versions')
    op.drop_index(op.f('ix_agents_versions_key'), table_name='agents_versions')
    op.drop_index('ix_agents_versions_expired_at', table_name='agents_versions')
    op.drop_table('agents_versions')
    op.drop_index('ix_agents_updated_at', table_name='agents')
    op.drop_index('ix_agents_key_prefix', table_name='agents')
    op.drop_index(op.f('ix_agents_key'), table_name='agents')
    op.drop_index('ix_agents_expired_at', table_name='agents')
    op.drop_table('agents')
    op.drop_index('ix_agent_states_updated_at', table_name='agent_states')
    op.drop_index('ix_agent_states_store_id', table_name='agent_states')
    op.drop_index(op.f('ix_agent_states_session_id'), table_name='agent_states')
    op.drop_table('agent_states')
    op.drop_index(op.f('ix_access_requests_resource_id'), table_name='access_requests')
    op.drop_index(op.f('ix_access_requests_requester_id'), table_name='access_requests')
    op.drop_index(op.f('ix_access_requests_requester_company_id'), table_name='access_requests')
    op.drop_index(op.f('ix_access_requests_owner_id'), table_name='access_requests')
    op.drop_index(op.f('ix_access_requests_company_id'), table_name='access_requests')
    op.drop_index('idx_access_requests_resource', table_name='access_requests')
    op.drop_index('idx_access_requests_owner_status', table_name='access_requests')
    op.drop_table('access_requests')
    op.drop_index(op.f('ix_access_grants_target_user_id'), table_name='access_grants')
    op.drop_index(op.f('ix_access_grants_target_company_id'), table_name='access_grants')
    op.drop_index(op.f('ix_access_grants_resource_id'), table_name='access_grants')
    op.drop_index(op.f('ix_access_grants_company_id'), table_name='access_grants')
    op.drop_index('idx_grants_token', table_name='access_grants')
    op.drop_index('idx_grants_target_user', table_name='access_grants')
    op.drop_index('idx_grants_target_company', table_name='access_grants')
    op.drop_index('idx_grants_resource', table_name='access_grants')
    op.drop_table('access_grants')
    # ### end Alembic commands ###

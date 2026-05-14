"""crm_tasks: единая таблица задач (заменяет crm_knowledge_imports)

Revision ID: crm_0016
Revises: crm_0015
Create Date: 2026-04-12
"""

from typing import Sequence, Union

from alembic import op

revision: str = "crm_0016"
down_revision: Union[str, None] = "crm_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE crm_tasks (
            task_id VARCHAR(100) NOT NULL PRIMARY KEY,
            task_type VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            stage VARCHAR(64) NOT NULL DEFAULT 'pending',
            progress_pct INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            data JSONB NOT NULL DEFAULT '{}',
            taskiq_task_id VARCHAR(220),
            cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
            company_id VARCHAR(100) NOT NULL,
            namespace VARCHAR(100) NOT NULL,
            user_id VARCHAR(100) NOT NULL,
            started_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_crm_tasks_company_id ON crm_tasks (company_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_crm_tasks_namespace ON crm_tasks (namespace)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_crm_tasks_status ON crm_tasks (status)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_crm_tasks_company_ns_status ON crm_tasks (company_id, namespace, status)
        """
    )
    op.execute(
        """
        INSERT INTO crm_tasks (
            task_id, task_type, status, stage, progress_pct,
            error_message, data, taskiq_task_id, cancel_requested,
            company_id, namespace, user_id,
            started_at, completed_at, created_at, updated_at
        )
        SELECT
            import_id,
            'knowledge_import',
            status,
            CASE
                WHEN status = 'pending' THEN 'pending'
                WHEN status = 'running' THEN 'processing_chunks'
                WHEN status = 'completed' THEN 'completed'
                WHEN status = 'failed' THEN 'failed'
                WHEN status = 'cancelled' THEN 'cancelled'
                WHEN status = 'rolled_back' THEN 'rolled_back'
                ELSE 'pending'
            END,
            CASE
                WHEN status = 'completed' THEN 100
                WHEN status IN ('failed', 'cancelled', 'rolled_back') THEN 100
                WHEN status = 'running' THEN 50
                ELSE 0
            END,
            error_message,
            jsonb_build_object(
                'mode', mode,
                'source_file_id', source_file_id,
                'source_file_ids', COALESCE(source_file_ids, '[]'::jsonb),
                'source_text_sha256', source_text_sha256,
                'split_by_headings', split_by_headings,
                'chunk_max_chars', chunk_max_chars,
                'extract_entity_types', extract_entity_types,
                'notes_created_count', notes_created_count,
                'entities_created_count', entities_created_count,
                'relationships_created_count', relationships_created_count,
                'created_entity_ids', COALESCE(created_entity_ids, '[]'::jsonb),
                'created_relationship_ids', COALESCE(created_relationship_ids, '[]'::jsonb),
                'attachment_document_ids', COALESCE(attachment_document_ids, '[]'::jsonb),
                'review_completed_at', to_jsonb(review_completed_at),
                'chunk_errors', COALESCE(chunk_errors, '[]'::jsonb)
            ),
            taskiq_task_id,
            cancel_requested,
            company_id,
            namespace,
            user_id,
            started_at,
            completed_at,
            created_at,
            updated_at
        FROM crm_knowledge_imports
        """
    )
    op.execute("DROP TABLE crm_knowledge_imports")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE crm_knowledge_imports (
            import_id VARCHAR(100) NOT NULL PRIMARY KEY,
            company_id VARCHAR(100) NOT NULL,
            namespace VARCHAR(100) NOT NULL,
            user_id VARCHAR(100) NOT NULL,
            mode VARCHAR(32) NOT NULL,
            status VARCHAR(32) NOT NULL,
            extract_entity_types JSONB,
            source_file_id VARCHAR(100),
            source_file_ids JSONB,
            source_text_sha256 VARCHAR(64),
            split_by_headings BOOLEAN NOT NULL DEFAULT FALSE,
            chunk_max_chars INTEGER NOT NULL DEFAULT 50000,
            taskiq_task_id VARCHAR(220),
            notes_created_count INTEGER NOT NULL DEFAULT 0,
            entities_created_count INTEGER NOT NULL DEFAULT 0,
            relationships_created_count INTEGER NOT NULL DEFAULT 0,
            created_entity_ids JSONB NOT NULL DEFAULT '[]',
            created_relationship_ids JSONB NOT NULL DEFAULT '[]',
            attachment_document_ids JSONB NOT NULL DEFAULT '[]',
            cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
            error_message TEXT,
            chunk_errors JSONB,
            started_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE,
            review_completed_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        INSERT INTO crm_knowledge_imports
        SELECT
            task_id, company_id, namespace, user_id,
            (data->>'mode')::VARCHAR(32),
            status,
            (data->'extract_entity_types'),
            (data->>'source_file_id'),
            (data->'source_file_ids'),
            (data->>'source_text_sha256'),
            COALESCE((data->>'split_by_headings')::boolean, false),
            COALESCE((data->>'chunk_max_chars')::integer, 50000),
            taskiq_task_id,
            COALESCE((data->>'notes_created_count')::integer, 0),
            COALESCE((data->>'entities_created_count')::integer, 0),
            COALESCE((data->>'relationships_created_count')::integer, 0),
            COALESCE(data->'created_entity_ids', '[]'::jsonb),
            COALESCE(data->'created_relationship_ids', '[]'::jsonb),
            COALESCE(data->'attachment_document_ids', '[]'::jsonb),
            cancel_requested,
            error_message,
            (data->'chunk_errors'),
            started_at,
            completed_at,
            (data->>'review_completed_at')::TIMESTAMP WITH TIME ZONE,
            created_at,
            updated_at
        FROM crm_tasks
        WHERE task_type = 'knowledge_import'
        """
    )
    op.execute("DROP TABLE crm_tasks")

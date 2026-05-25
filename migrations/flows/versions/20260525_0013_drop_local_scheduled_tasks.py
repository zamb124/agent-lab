"""drop flows-local scheduled_tasks projection (source of truth — shared scheduler_tasks)

Revision ID: 20260525_0013
Revises: 20260525_0012
Create Date: 2026-05-25
"""

from __future__ import annotations

from alembic import op

revision = "20260525_0013"
down_revision = "20260525_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Платформенный source of truth — core.db.models.platform.SchedulerTaskRecord
    # (таблица scheduler_tasks в shared БД). Локальная проекция в flows БД больше
    # не нужна: ScheduleService и execute_scheduled_task работают напрямую через
    # core.scheduler.SchedulerTaskRepository.
    op.execute("DROP INDEX IF EXISTS ix_scheduled_tasks_session_id")
    op.execute("DROP INDEX IF EXISTS ix_scheduled_tasks_flow_id")
    op.execute("DROP INDEX IF EXISTS ix_scheduled_tasks_status")
    op.execute("DROP INDEX IF EXISTS ix_scheduled_tasks_next_run")
    op.execute("DROP TABLE IF EXISTS scheduled_tasks")


def downgrade() -> None:
    pass

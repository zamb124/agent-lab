"""drop operator_tasks, operator_queue_members, operator_queues

HITL переведён на платформенное ядро задач WorkItem (БД platform_worktracker).
Операторские таблицы flows больше не используются и удаляются.

Revision ID: 20260622_0021
Revises: 20260525_0020
Create Date: 2026-06-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260622_0021"
down_revision: Union[str, None] = "20260525_0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS operator_tasks CASCADE")
    op.execute("DROP TABLE IF EXISTS operator_queue_members CASCADE")
    op.execute("DROP TABLE IF EXISTS operator_queues CASCADE")


def downgrade() -> None:
    raise NotImplementedError(
        "operator_* удалены безвозвратно: HITL живёт в platform_worktracker (WorkItem)"
    )

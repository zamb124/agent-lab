"""drop crm_entities work columns (priority, due_date, assignees)

Work-семантика задач переехала в платформенное ядро WorkItem (kind=crm_activity,
БД platform_worktracker, связь 1:1 через CrmEntityLink). CRM-узел задачи остаётся
графовой сущностью; колонки приоритета/срока/исполнителей и индекс по due_date
удаляются. Канбан-статус (attributes.status) тоже больше не хранится на CRM-узле.

Запускать ПОСЛЕ scripts/migrate_to_worktracker.py (он читает эти колонки сырым SQL).

Revision ID: 20260622_0025
Revises: 1045cfb7c721
Create Date: 2026-06-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260622_0025"
down_revision: Union[str, None] = "1045cfb7c721"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_crm_entities_due_date")
    op.execute("ALTER TABLE crm_entities DROP COLUMN IF EXISTS priority")
    op.execute("ALTER TABLE crm_entities DROP COLUMN IF EXISTS due_date")
    op.execute("ALTER TABLE crm_entities DROP COLUMN IF EXISTS assignees")


def downgrade() -> None:
    raise NotImplementedError(
        "work-поля CRM-задач удалены безвозвратно: источник истины — WorkItem (platform_worktracker)"
    )

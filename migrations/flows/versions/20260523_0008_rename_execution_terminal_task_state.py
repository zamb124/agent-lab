"""ExecutionState terminal status fields -> terminal task state fields.

Revision ID: agents_0008
Revises: agents_0007
Create Date: 2026-05-23
"""

from typing import Sequence, Union

from alembic import op

revision: str = "agents_0008"
down_revision: Union[str, None] = "agents_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE states
        SET value = jsonb_set(
            value #- '{data,terminal_status}',
            '{data,terminal_task_state}',
            value #> '{data,terminal_status}',
            true
        )
        WHERE value->'data' ? 'terminal_status'
        """
    )
    op.execute(
        """
        UPDATE states
        SET value = jsonb_set(
            value #- '{data,terminal_error}',
            '{data,terminal_task_error}',
            value #> '{data,terminal_error}',
            true
        )
        WHERE value->'data' ? 'terminal_error'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE states
        SET value = jsonb_set(
            value #- '{data,terminal_task_state}',
            '{data,terminal_status}',
            value #> '{data,terminal_task_state}',
            true
        )
        WHERE value->'data' ? 'terminal_task_state'
        """
    )
    op.execute(
        """
        UPDATE states
        SET value = jsonb_set(
            value #- '{data,terminal_task_error}',
            '{data,terminal_error}',
            value #> '{data,terminal_task_error}',
            true
        )
        WHERE value->'data' ? 'terminal_task_error'
        """
    )

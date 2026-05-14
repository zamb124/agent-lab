"""Drop sync_spaces: каналы и записи звонков переезжают на строковое поле namespace.

Sync space = platform namespace 1:1. Источник правды — `NamespaceRepository`
из shared (`apps/crm/api/namespaces.py` создаёт/обновляет, sync только
читает и пишет свою секцию `Namespace.sync_settings`). Строковое поле
`namespace` живёт прямо на каналах/записях звонков, без отдельной таблицы.

Состав:
  1. Колонка `namespace` в `sync_channels` и `sync_call_recordings`,
     backfill из `sync_spaces.namespace` через JOIN. Direct-каналы и
     записи без `space_id` получают `'default'` (фолбек на дефолтный
     namespace компании).
  2. Дроп FK/индексов `space_id` и колонок `space_id` в `sync_channels` и
     `sync_call_recordings`.
  3. Дроп индексов и таблицы `sync_spaces`.

Перенос настроек `transcribe_voice_messages` / `speech_to_chat_enabled`
выполняется на shared-уровне (поле `Namespace.sync_settings` в core
модели). По умолчанию настройки выключены; если для namespace они должны
быть включены — выставить через PUT `/sync/api/v1/namespaces/{name}` после
прогона миграции.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "sync_0016"
down_revision: Union[str, None] = "sync_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sync_channels",
        sa.Column("namespace", sa.String(length=100), nullable=True),
    )
    op.execute(
        "UPDATE sync_channels c "
        "SET namespace = COALESCE("
        "(SELECT s.namespace FROM sync_spaces s WHERE s.space_id = c.space_id),"
        "'default')"
    )
    op.alter_column(
        "sync_channels",
        "namespace",
        existing_type=sa.String(length=100),
        nullable=False,
    )
    op.create_index(
        "ix_sync_channels_company_namespace",
        "sync_channels",
        ["company_id", "namespace"],
    )
    op.drop_index("ix_sync_channels_space", table_name="sync_channels")
    op.drop_constraint(
        "sync_channels_space_id_fkey",
        "sync_channels",
        type_="foreignkey",
    )
    op.drop_column("sync_channels", "space_id")

    op.add_column(
        "sync_call_recordings",
        sa.Column("namespace", sa.String(length=100), nullable=True),
    )
    op.execute(
        "UPDATE sync_call_recordings r "
        "SET namespace = COALESCE("
        "(SELECT s.namespace FROM sync_spaces s WHERE s.space_id = r.space_id),"
        "'default')"
    )
    op.alter_column(
        "sync_call_recordings",
        "namespace",
        existing_type=sa.String(length=100),
        nullable=False,
    )
    op.create_index(
        "ix_sync_call_recordings_company_namespace",
        "sync_call_recordings",
        ["company_id", "namespace"],
    )
    op.drop_constraint(
        "sync_call_recordings_space_id_fkey",
        "sync_call_recordings",
        type_="foreignkey",
    )
    op.drop_column("sync_call_recordings", "space_id")

    op.drop_index("idx_sync_spaces_company_namespace", table_name="sync_spaces")
    op.drop_index("ix_sync_spaces_company", table_name="sync_spaces")
    op.drop_table("sync_spaces")


def downgrade() -> None:
    op.create_table(
        "sync_spaces",
        sa.Column("space_id", sa.String(length=100), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("namespace", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.String(length=100), nullable=True),
        sa.Column(
            "transcribe_voice_messages",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "speech_to_chat_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_index("ix_sync_spaces_company", "sync_spaces", ["company_id"])
    op.create_index(
        "idx_sync_spaces_company_namespace",
        "sync_spaces",
        ["company_id", "namespace"],
        unique=True,
    )

    op.add_column(
        "sync_call_recordings",
        sa.Column("space_id", sa.String(length=100), nullable=True),
    )
    op.create_foreign_key(
        "sync_call_recordings_space_id_fkey",
        "sync_call_recordings",
        "sync_spaces",
        ["space_id"],
        ["space_id"],
        ondelete="SET NULL",
    )
    op.drop_index(
        "ix_sync_call_recordings_company_namespace",
        table_name="sync_call_recordings",
    )
    op.drop_column("sync_call_recordings", "namespace")

    op.add_column(
        "sync_channels",
        sa.Column("space_id", sa.String(length=100), nullable=True),
    )
    op.create_foreign_key(
        "sync_channels_space_id_fkey",
        "sync_channels",
        "sync_spaces",
        ["space_id"],
        ["space_id"],
    )
    op.create_index("ix_sync_channels_space", "sync_channels", ["space_id"])
    op.drop_index("ix_sync_channels_company_namespace", table_name="sync_channels")
    op.drop_column("sync_channels", "namespace")

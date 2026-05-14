"""company_voice_providers: per-company override провайдеров речи

Revision ID: shared_0009
Revises: shared_0008
Create Date: 2026-05-03

Создаёт таблицу `company_voice_providers (company_id, kind, provider, ...)`.
Использование — `core.clients.voice_resolver` через
`CompanyVoiceProvidersRepository` в core/db.shared. Записи переопределяют
deployment-default из `settings.voice.<kind>` для конкретной компании;
per-call переопределение делается через `SpeechOverride` (см.
`core.clients.speech_override`).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "shared_0009"
down_revision: Union[str, None] = "shared_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_voice_providers",
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("voice", sa.String(), nullable=True),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column("sample_rate", sa.Integer(), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("response_format", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("company_id", "kind", name="company_voice_providers_pk"),
        sa.CheckConstraint(
            "kind IN ('stt','tts','vad')",
            name="company_voice_providers_kind_check",
        ),
        sa.CheckConstraint(
            "provider IN ('litserve','cloud_ru','yandex','sber','silero_local','mock')",
            name="company_voice_providers_provider_check",
        ),
    )
    op.create_index(
        "ix_company_voice_providers_company_id",
        "company_voice_providers",
        ["company_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_voice_providers_company_id", table_name="company_voice_providers"
    )
    op.drop_table("company_voice_providers")

"""Replace persisted embed chat_override with interface_override.

Revision ID: shared_0029
Revises: shared_0028
Create Date: 2026-08-04
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import cast

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from core.models.embed_models import EmbedConfig
from core.models.flow_interface_migration import (
    migrate_embed_config_payload,
    reconstruct_removed_embed_override,
)
from core.types import JsonObject, require_json_object

revision: str = "shared_0029"
down_revision: str | None = "shared_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rewrite(
    transform: Callable[[JsonObject], JsonObject],
    *,
    predicate: str,
    validate_current: bool,
) -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT key, value FROM storage WHERE "
            + "key LIKE 'company:%:embed_config:%' AND "
            + predicate
        )
    ).mappings()
    update_statement = sa.text(
        "UPDATE storage SET value = :value, updated_at = now() WHERE key = :key"
    ).bindparams(sa.bindparam("value", type_=postgresql.JSONB()))
    for row in rows:
        key_value = cast(object, row["key"])
        if not isinstance(key_value, str):
            raise RuntimeError("Embed Flow UI migration found an invalid storage key")
        key = key_value
        payload = require_json_object(cast(object, row["value"]), f"storage.{key}")
        try:
            migrated = transform(payload)
            if validate_current:
                _ = EmbedConfig.model_validate(migrated)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Embed Flow UI migration failed for storage.{key}") from exc
        _ = connection.execute(update_statement, {"key": key, "value": migrated})


def upgrade() -> None:
    _rewrite(
        migrate_embed_config_payload,
        predicate="value ? 'chat_override'",
        validate_current=True,
    )


def downgrade() -> None:
    _rewrite(
        reconstruct_removed_embed_override,
        predicate="value ? 'interface_override'",
        validate_current=False,
    )

"""Replace persisted FlowConfig.chat with the editable Flow UI template.

Revision ID: 20260804_0029
Revises: 20260804_0028
Create Date: 2026-08-04
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import cast

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from apps.flows.src.models.flow_config import FlowConfig
from core.models.flow_interface_migration import (
    migrate_flow_config_payload,
    reconstruct_removed_chat_settings,
)
from core.types import JsonObject, require_json_object

revision: str = "20260804_0029"
down_revision: str | None = "20260804_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rewrite(
    transform: Callable[[JsonObject], JsonObject],
    *,
    predicate: str,
    validate_current: bool,
) -> None:
    connection = op.get_bind()
    value_parameter = sa.bindparam("value", type_=postgresql.JSONB())
    for table in ("flows", "flows_versions"):
        rows = connection.execute(
            sa.text(f"SELECT key, value FROM {table} WHERE {predicate}")
        ).mappings()
        update_statement = sa.text(
            f"UPDATE {table} SET value = :value, updated_at = now() WHERE key = :key"
        ).bindparams(value_parameter)
        for row in rows:
            key_value = cast(object, row["key"])
            if not isinstance(key_value, str):
                raise RuntimeError(f"Flow UI config migration found invalid key in {table}")
            key = key_value
            payload = require_json_object(
                cast(object, row["value"]),
                f"{table}.{key}",
            )
            try:
                migrated = transform(payload)
                if validate_current:
                    _ = FlowConfig.model_validate(migrated)
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"Flow UI config migration failed for {table}.{key}") from exc
            _ = connection.execute(update_statement, {"key": key, "value": migrated})


def upgrade() -> None:
    _rewrite(
        migrate_flow_config_payload,
        predicate="value ? 'chat'",
        validate_current=True,
    )


def downgrade() -> None:
    _rewrite(
        reconstruct_removed_chat_settings,
        predicate="value ? 'interface'",
        validate_current=False,
    )

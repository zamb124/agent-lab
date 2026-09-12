"""Embed configs store presentation and launcher position as separate typed fields.

``position=fullscreen`` used to mean a full-page mount; now ``presentation=page`` carries that
meaning and ``position`` is only a launcher corner (``bottom-right`` | ``bottom-left``).

Revision ID: shared_0035
Revises: shared_0034
Create Date: 2026-09-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from core.models.embed_models import EmbedConfig
from core.types import JsonObject, require_json_object

revision: str = "shared_0035"
down_revision: str | None = "shared_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LAUNCHER_POSITIONS = ("bottom-right", "bottom-left")


def _canonical_embed_config(payload: JsonObject) -> JsonObject:
    position = payload.get("position")
    if not isinstance(position, str):
        raise ValueError("position must be a string")
    if position.strip().lower() == "fullscreen":
        payload["presentation"] = "page"
        payload["position"] = "bottom-right"
    elif position not in _LAUNCHER_POSITIONS:
        payload["position"] = "bottom-right"
    return payload


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT key, value FROM storage WHERE key LIKE 'company:%:embed_config:%' "
            "AND value->>'position' NOT IN ('bottom-right', 'bottom-left')"
        )
    ).mappings().all()
    update_statement = sa.text(
        "UPDATE storage SET value = :value, updated_at = now() WHERE key = :key"
    ).bindparams(sa.bindparam("value", type_=postgresql.JSONB()))
    for row in rows:
        key = row["key"]
        if not isinstance(key, str):
            raise RuntimeError("Embed position migration found an invalid storage key")
        payload = require_json_object(row["value"], f"storage.{key}")
        try:
            migrated = _canonical_embed_config(payload)
            _ = EmbedConfig.model_validate(migrated)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Embed position migration failed for storage.{key}: {exc}") from exc
        _ = connection.execute(update_statement, {"key": key, "value": migrated})


def downgrade() -> None:
    raise RuntimeError(
        "Embed position canon cannot be reverted to position=fullscreen; "
        "restore the shared database from a backup taken before shared_0035"
    )

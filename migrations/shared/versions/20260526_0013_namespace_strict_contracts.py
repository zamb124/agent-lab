"""Normalize persisted namespace JSON to strict contracts.

Revision ID: shared_0013
Revises: shared_0012
Create Date: 2026-05-26

Runtime namespace models are strict. This migration rewrites persisted JSON
created by older UI contracts:
- CRM board stages: `id` -> `stage_id`
- Sidebar navigation entries: `id` -> `nav_id`
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "shared_0013"
down_revision: Union[str, None] = "shared_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalize_stage(raw: Any) -> Any:
    if not isinstance(raw, Mapping):
        return raw
    stage: dict[str, Any] = dict(raw)
    legacy_id = stage.pop("id", None)
    if "stage_id" not in stage and isinstance(legacy_id, str) and legacy_id.strip():
        stage["stage_id"] = legacy_id
    return stage


def _normalize_task_board_preset(raw: Any) -> Any:
    if not isinstance(raw, Mapping):
        return raw
    preset: dict[str, Any] = dict(raw)
    stages = preset.get("stages")
    if isinstance(stages, list):
        preset["stages"] = [_normalize_stage(stage) for stage in stages]
    return preset


def _normalize_sidebar_entry(raw: Any) -> Any:
    if not isinstance(raw, Mapping):
        return raw
    entry: dict[str, Any] = dict(raw)
    legacy_id = entry.pop("id", None)
    if "nav_id" not in entry and isinstance(legacy_id, str) and legacy_id.strip():
        entry["nav_id"] = legacy_id
    children = entry.get("children")
    if isinstance(children, list):
        entry["children"] = [_normalize_sidebar_entry(child) for child in children]
    return entry


def _normalize_namespace_value(raw: Any) -> Any:
    if not isinstance(raw, MutableMapping):
        return raw
    value: dict[str, Any] = dict(raw)
    crm_settings = value.get("crm_settings")
    if not isinstance(crm_settings, MutableMapping):
        return value

    crm: dict[str, Any] = dict(crm_settings)
    presets = crm.get("pipeline_stage_presets")
    if isinstance(presets, Mapping):
        crm["pipeline_stage_presets"] = {
            str(key): _normalize_task_board_preset(preset)
            for key, preset in presets.items()
        }

    navigation = crm.get("sidebar_navigation")
    if isinstance(navigation, list):
        crm["sidebar_navigation"] = [_normalize_sidebar_entry(entry) for entry in navigation]

    value["crm_settings"] = crm
    return value


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT key, value FROM namespaces")).mappings().all()
    update_stmt = sa.text(
        "UPDATE namespaces SET value = :value, updated_at = now() WHERE key = :key"
    ).bindparams(
        sa.bindparam("key", type_=sa.String()),
        sa.bindparam("value", type_=postgresql.JSONB()),
    )
    for row in rows:
        value = row["value"]
        normalized = _normalize_namespace_value(value)
        if normalized != value:
            connection.execute(update_stmt, {"key": row["key"], "value": normalized})


def downgrade() -> None:
    pass

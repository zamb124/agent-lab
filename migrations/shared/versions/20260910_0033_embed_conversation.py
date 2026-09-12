"""Embed configs describe the conversation block instead of an A2UI interface override.

Revision ID: shared_0033
Revises: shared_0032
Create Date: 2026-09-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from core.flow_ui.document import FlowUIConversationSettings
from core.models.embed_models import EmbedConfig
from core.types import JsonObject, JsonValue, require_json_object

revision: str = "shared_0033"
down_revision: str | None = "shared_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY_TO_SETTINGS: dict[str, str] = {
    "show_reasoning": "show_reasoning",
    "tool_calls_display": "tool_calls",
    "show_activity": "show_activity",
    "show_skill_loads": "show_skill_loads",
    "show_reflection": "show_reflection",
    "errors_display": "errors",
    "show_run_trace": "show_run_trace",
    "show_trace_actions": "show_trace_actions",
    "show_browser_previews": "show_browser_previews",
    "show_files_panel": "show_files_panel",
    "allow_cancel": "allow_cancel",
    "allow_voice": "allow_voice",
}


def _string_list(value: JsonValue, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{label} items must be strings")
        items.append(item)
    return items


def _convert_embed_config(payload: JsonObject) -> JsonObject:
    override = payload.pop("interface_override")
    payload.setdefault("conversation", None)
    payload.setdefault("start_page_id", None)
    if override is None:
        return payload
    override_object = require_json_object(override, "interface_override")
    policy_raw = override_object.get("policy")
    policy = {} if policy_raw is None else require_json_object(policy_raw, "interface_override.policy")
    content_raw = override_object.get("initial_content")
    content = {} if content_raw is None else require_json_object(content_raw, "interface_override.initial_content")

    settings: JsonObject = {}
    for policy_name, settings_name in _POLICY_TO_SETTINGS.items():
        if policy.get(policy_name) is not None:
            settings[settings_name] = policy[policy_name]
    greeting = content.get("greeting")
    if isinstance(greeting, str) and greeting:
        settings["greeting"] = greeting
    prompts = content.get("suggestedPrompts")
    if prompts is not None:
        settings["suggested_prompts"] = _string_list(prompts, "initial_content.suggestedPrompts")[:12]
    if settings:
        payload["conversation"] = FlowUIConversationSettings.model_validate(settings).model_dump(mode="json")
    initial_page_id = policy.get("initial_page_id")
    if isinstance(initial_page_id, str) and initial_page_id:
        payload["start_page_id"] = initial_page_id
    return payload


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT key, value FROM storage WHERE key LIKE 'company:%:embed_config:%' "
            "AND value ? 'interface_override'"
        )
    ).mappings().all()
    update_statement = sa.text(
        "UPDATE storage SET value = :value, updated_at = now() WHERE key = :key"
    ).bindparams(sa.bindparam("value", type_=postgresql.JSONB()))
    for row in rows:
        key = row["key"]
        if not isinstance(key, str):
            raise RuntimeError("Embed conversation migration found an invalid storage key")
        payload = require_json_object(row["value"], f"storage.{key}")
        try:
            migrated = _convert_embed_config(payload)
            _ = EmbedConfig.model_validate(migrated)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Embed conversation migration failed for storage.{key}: {exc}") from exc
        _ = connection.execute(update_statement, {"key": key, "value": migrated})


def downgrade() -> None:
    raise RuntimeError(
        "Embed conversation settings cannot be converted back to A2UI interface overrides; "
        "restore the shared database from a backup taken before shared_0033"
    )

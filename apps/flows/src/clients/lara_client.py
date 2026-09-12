"""LaraClient — confirm-first propose/apply for Lara actions in the flows process."""

from __future__ import annotations

from apps.flows.src.container_state import require_current_container
from apps.flows.src.runtime_helpers.flow_ui_cards import show_action_preview, show_action_result
from core.context import resolve_namespace_or_raise
from core.state import ExecutionState
from core.types import JsonObject, require_json_object


class LaraClient:
    """In-process client for LaraFacade preview/apply (CRM note, etc.)."""

    async def propose_create_note(
        self,
        *,
        name: str,
        description: str,
        note_date: str | None,
        namespace: str | None,
        state: ExecutionState,
        idempotency_key: str | None = None,
    ) -> JsonObject:
        ns = namespace if namespace and str(namespace).strip() else resolve_namespace_or_raise()
        facade = require_current_container().lara_facade
        action = await facade.preview_crm_create_note(
            name=name.strip(),
            description=description,
            note_date=note_date,
            namespace=ns,
            state=state,
            idempotency_key=idempotency_key,
        )
        action_payload = require_json_object(
            action.model_dump(mode="json"),
            "crm.note.preview.action",
        )
        action_button: JsonObject = {
            "action_id": "crm.note.create.apply",
            "action_kind": "apply",
            "label": "Создать заметку",
            "pending_action_id": action.pending_action_id,
            "arguments": {"pending_action_id": action.pending_action_id},
            "context": {"capability": "crm.note", "operation": "create"},
        }
        preview_blocks: list[JsonObject] = [
            {"type": "text", "text": "Черновик создания заметки готов. Подтвердите применение."},
            {"type": "actions", "buttons": [action_button]},
        ]
        _ = show_action_preview(
            state,
            card_id=f"crm-note-preview-{action.pending_action_id}",
            title="Создание заметки CRM",
            summary="Черновик создания заметки готов. Подтвердите применение.",
            parameters=action_payload,
            apply_action="apply_pending_action",
            apply_payload={"pending_action_id": action.pending_action_id, "capability": "crm.note"},
            apply_label="Создать заметку",
        )
        return {
            "mode": "propose",
            "pending_action_id": action.pending_action_id,
            "action": action_payload,
            "blocks": preview_blocks,
        }

    async def apply_create_note(
        self,
        *,
        pending_action_id: str,
        state: ExecutionState,
        idempotency_key: str | None = None,
    ) -> JsonObject:
        facade = require_current_container().lara_facade
        action = await facade.apply_crm_create_note(
            pending_action_id=pending_action_id,
            state=state,
            idempotency_key=idempotency_key,
        )
        result_payload = action.result
        if result_payload is None:
            raise ValueError("Invalid apply result payload")
        entity_raw = result_payload.get("entity")
        if not isinstance(entity_raw, dict):
            raise ValueError("CRM create note: invalid response")
        entity = require_json_object(entity_raw, "crm.note.apply.entity")
        eid = entity.get("entity_id")
        if not isinstance(eid, str) or not eid.strip():
            raise ValueError("CRM create note: missing entity_id")
        open_entity_button: JsonObject = {
            "action_id": "crm.entity.open",
            "action_kind": "open_entity",
            "label": "Открыть сущность",
            "arguments": {"entity_id": eid},
            "context": {"entity_id": eid, "entity_type": "note"},
        }
        result: JsonObject = {
            "mode": "apply",
            "pending_action_id": pending_action_id,
            "entity_id": eid,
            "entity": entity,
            "blocks": [
                {
                    "type": "card",
                    "title": entity.get("name") or "Note",
                    "subtitle": eid,
                },
                {"type": "actions", "buttons": [open_entity_button]},
            ],
        }
        _ = show_action_result(
            state,
            card_id=f"crm-note-apply-{pending_action_id}",
            title="Заметка CRM создана",
            status="success",
            summary=f"Сущность {eid}",
        )
        return result

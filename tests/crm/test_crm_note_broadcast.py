"""CRM note domain push: один факт = одна запись `publish_event_to_users`."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import cast

import pytest
from pytest import MonkeyPatch

from apps.crm.constants_graph import NOTE_ROOT_ENTITY_TYPE_ID
from apps.crm.db.models import CRMEntity
from apps.crm.services import crm_note_broadcast as broadcast_mod
from core.types import JsonObject, JsonValue


def _sample_note() -> CRMEntity:
    now = datetime.now(UTC)
    return CRMEntity(
        entity_id="note_1",
        company_id="company_1",
        namespace="default",
        entity_type=NOTE_ROOT_ENTITY_TYPE_ID,
        entity_subtype="meeting",
        name="Sample note",
        description="body",
        status="active",
        tags=[],
        attributes={},
        note_date=date(2026, 7, 23),
        attachment_ids=[],
        user_id="user_a",
        relevance=1.0,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_broadcast_crm_note_event_one_stream_entry(
    monkeypatch: MonkeyPatch,
) -> None:
    publish_calls: list[tuple[list[str], str, JsonObject]] = []
    notify_calls: list[str] = []

    async def _resolve(
        *,
        company_id: str,
        namespace: str,
        company_repository: object,
        access_grant_repository: object,
    ) -> list[str]:
        _ = (company_id, namespace, company_repository, access_grant_repository)
        return ["user_a", "user_b", "user_c"]

    async def _publish(
        user_ids: list[str],
        event_type: str,
        payload: JsonValue,
        **kwargs: object,
    ) -> None:
        _ = kwargs
        if not isinstance(payload, dict):
            raise AssertionError("payload must be object")
        publish_calls.append((list(user_ids), event_type, cast(JsonObject, payload)))

    async def _notify(*, user_id: str, notification: object) -> None:
        _ = notification
        notify_calls.append(user_id)

    monkeypatch.setattr(broadcast_mod, "resolve_user_ids_for_namespace_broadcast", _resolve)
    monkeypatch.setattr(broadcast_mod, "publish_event_to_users", _publish)
    monkeypatch.setattr(broadcast_mod, "notify_user", _notify)

    await broadcast_mod.broadcast_crm_note_event(
        company_id="company_1",
        namespace="default",
        note_id="note_1",
        note_date_iso="2026-07-23",
        action="updated",
        note=_sample_note(),
        company_repository=object(),
        access_grant_repository=object(),
    )

    assert len(publish_calls) == 1
    recipients, event_type, payload = publish_calls[0]
    assert event_type == "crm/note/updated"
    assert recipients == ["user_a", "user_b", "user_c"]
    assert payload["note_id"] == "note_1"
    note_payload = payload.get("note")
    assert isinstance(note_payload, dict)
    assert note_payload["entity_id"] == "note_1"
    assert notify_calls == ["user_a", "user_b", "user_c"]


@pytest.mark.asyncio
async def test_broadcast_crm_note_event_deleted_without_note(
    monkeypatch: MonkeyPatch,
) -> None:
    publish_calls: list[JsonObject] = []

    async def _resolve(
        *,
        company_id: str,
        namespace: str,
        company_repository: object,
        access_grant_repository: object,
    ) -> list[str]:
        _ = (company_id, namespace, company_repository, access_grant_repository)
        return ["user_a"]

    async def _publish(
        user_ids: list[str],
        event_type: str,
        payload: JsonValue,
        **kwargs: object,
    ) -> None:
        _ = (user_ids, event_type, kwargs)
        if not isinstance(payload, dict):
            raise AssertionError("payload must be object")
        publish_calls.append(cast(JsonObject, payload))

    async def _notify(*, user_id: str, notification: object) -> None:
        _ = (user_id, notification)

    monkeypatch.setattr(broadcast_mod, "resolve_user_ids_for_namespace_broadcast", _resolve)
    monkeypatch.setattr(broadcast_mod, "publish_event_to_users", _publish)
    monkeypatch.setattr(broadcast_mod, "notify_user", _notify)

    await broadcast_mod.broadcast_crm_note_event(
        company_id="company_1",
        namespace="default",
        note_id="note_1",
        note_date_iso="2026-07-23",
        action="deleted",
        company_repository=object(),
        access_grant_repository=object(),
    )

    assert len(publish_calls) == 1
    assert publish_calls[0]["action"] == "deleted"
    assert "note" not in publish_calls[0]

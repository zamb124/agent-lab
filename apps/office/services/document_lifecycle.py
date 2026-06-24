"""Lifecycle операции Documents: item mapping, events, shares."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apps.office.container import OfficeContainer
from apps.office.db.models import OfficeDocumentBinding
from apps.office.models.api import OfficeDocumentItem
from core.models.identity_models import User
from core.types import JsonObject


async def binding_to_item(
    container: OfficeContainer,
    row: OfficeDocumentBinding,
    users_by_id: dict[str, User] | None = None,
) -> OfficeDocumentItem:
    author = users_by_id.get(row.created_by_user_id) if users_by_id else None
    if author is None:
        loaded = await container.user_repository.get(row.created_by_user_id)
        if loaded is not None:
            author = loaded
    if author is not None:
        display_name = author.name
        avatar_url = author.avatar_url
    else:
        display_name = row.created_by_user_id
        avatar_url = None
    file_record = await container.file_repository.get(row.file_id)
    if file_record is None:
        raise ValueError(f"FileRecord не найден для binding {row.binding_id}")
    updated_at = file_record.updated_at
    return OfficeDocumentItem(
        binding_id=row.binding_id,
        catalog_id=row.catalog_id,
        title=row.title,
        file_id=row.file_id,
        file_category=row.file_category,
        onlyoffice_document_type=row.onlyoffice_document_type,
        file_size=file_record.file_size,
        created_at=row.created_at,
        updated_at=updated_at,
        created_by_user_id=row.created_by_user_id,
        created_by_display_name=display_name,
        created_by_avatar_url=avatar_url,
    )


async def bindings_to_items(
    container: OfficeContainer,
    rows: list[OfficeDocumentBinding],
) -> list[OfficeDocumentItem]:
    user_ids = {row.created_by_user_id for row in rows}
    users_by_id: dict[str, User] = {}
    for uid in user_ids:
        loaded = await container.user_repository.get(uid)
        if loaded is not None:
            users_by_id[uid] = loaded
    items: list[OfficeDocumentItem] = []
    for row in rows:
        items.append(await binding_to_item(container, row, users_by_id))
    return items


async def record_document_event(
    container: OfficeContainer,
    *,
    binding_id: str,
    company_id: str,
    event_type: str,
    user_id: str,
    payload: JsonObject | None = None,
) -> None:
    event_payload: JsonObject = payload if payload is not None else {}
    _ = await container.document_event_repository.append(
        binding_id=binding_id,
        company_id=company_id,
        event_type=event_type,
        user_id=user_id,
        payload=event_payload,
    )


def share_expires_at(expires_in_hours: int | None) -> datetime | None:
    if expires_in_hours is None:
        return None
    return datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)

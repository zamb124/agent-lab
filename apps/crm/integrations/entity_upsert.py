"""
Идемпотентный upsert канонической сущности по внешнему ref: (namespace, type, source, record_id).
Возвращает (сущность, created): created True только при первом создании записи.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from apps.crm.constants_graph import NOTE_ROOT_ENTITY_TYPE_ID
from apps.crm.db.models import CRMEntity
from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.crm.integrations.external_ref import external_ref_now, merge_external_refs
from apps.crm.types import JsonObject


async def upsert_canonical_by_external_ref(
    *,
    entity_repo: EntityRepository,
    namespace: str,
    company_id: str,
    user_id: str,
    entity_type: str,
    source_id: str,
    record_id: str,
    name: str,
    patch_attributes: JsonObject,
    account_key: str | None = None,
    raw_version: str | None = None,
    description: str | None = None,
    note_date: date | None = None,
    due_date: date | None = None,
) -> tuple[CRMEntity, bool]:
    rid = str(record_id).strip()
    if not rid:
        raise ValueError("record_id обязателен")
    if "external_refs" in patch_attributes:
        raise ValueError("patch_attributes не должен содержать external_refs")

    ref = external_ref_now(record_id=rid, account_key=account_key, raw_version=raw_version)

    existing_list = await entity_repo.find_by_external_ref(
        company_id=company_id,
        namespace=namespace,
        entity_type=entity_type,
        source_id=source_id,
        record_id=rid,
    )
    if len(existing_list) > 1:
        raise ValueError(
            f"Несколько сущностей для ref {source_id}/{rid} в {namespace}/{entity_type}"
        )

    if existing_list:
        ent = existing_list[0]
        base_attrs = dict(ent.attributes) if ent.attributes else {}
        merged_attrs = merge_external_refs(base_attrs, source_id=source_id, ref=ref)
        for key, value in patch_attributes.items():
            merged_attrs[key] = value
        ent.name = name
        ent.attributes = merged_attrs
        ent.namespace = namespace
        ent.updated_at = datetime.now(UTC)
        if description is not None:
            ent.description = description
        if note_date is not None:
            ent.note_date = note_date
        elif entity_type == NOTE_ROOT_ENTITY_TYPE_ID and ent.note_date is None:
            ent.note_date = datetime.now(UTC).date()
        if due_date is not None:
            ent.due_date = due_date
        updated = await entity_repo.update(ent)
        return updated, False

    initial_attrs = merge_external_refs({}, source_id=source_id, ref=ref)
    for key, value in patch_attributes.items():
        initial_attrs[key] = value
    effective_note_date = note_date
    if entity_type == NOTE_ROOT_ENTITY_TYPE_ID and effective_note_date is None:
        effective_note_date = datetime.now(UTC).date()
    ent = CRMEntity(
        entity_id=uuid.uuid4().hex,
        company_id=company_id,
        namespace=namespace,
        entity_type=entity_type,
        name=name,
        description=description,
        attributes=initial_attrs,
        tags=[],
        user_id=user_id,
        note_date=effective_note_date,
        due_date=due_date,
    )
    created = await entity_repo.create(ent)
    return created, True

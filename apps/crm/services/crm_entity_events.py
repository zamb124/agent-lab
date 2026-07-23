"""Доменные события CRM entity на шине `platform:events`.

`crm/entity/created|updated|deleted` — чисто доменные события (`delivery=None`):
UI-обновления CRM живут отдельными push-событиями (notes/tasks/summary),
а эти события существуют для durable-потребителей шины — прежде всего
триггеров flows («flow возбуждается от создания entity в Networkle»).
"""

from __future__ import annotations

from pydantic import BaseModel

from apps.crm.db.models import CRMEntity
from core.events import publish_domain_event, register_platform_event

CRM_ENTITY_CREATED = "crm/entity/created"
CRM_ENTITY_UPDATED = "crm/entity/updated"
CRM_ENTITY_DELETED = "crm/entity/deleted"


class CrmEntityEventPayload(BaseModel):
    """Payload событий `crm/entity/*`."""

    entity_id: str
    entity_type: str
    entity_subtype: str | None
    namespace: str
    name: str
    status: str
    tags: list[str]
    actor_user_id: str


register_platform_event(
    CRM_ENTITY_CREATED,
    CrmEntityEventPayload,
    description="Создана сущность CRM (person/organization/task/note/...).",
)
register_platform_event(
    CRM_ENTITY_UPDATED,
    CrmEntityEventPayload,
    description="Обновлена сущность CRM.",
)
register_platform_event(
    CRM_ENTITY_DELETED,
    CrmEntityEventPayload,
    description="Удалена сущность CRM.",
)


async def publish_crm_entity_event(event_type: str, entity: CRMEntity) -> None:
    """Опубликовать доменное событие по CRM entity."""
    payload = CrmEntityEventPayload(
        entity_id=entity.entity_id,
        entity_type=entity.entity_type,
        entity_subtype=entity.entity_subtype,
        namespace=entity.namespace,
        name=entity.name,
        status=entity.status,
        tags=list(entity.tags),
        actor_user_id=entity.user_id,
    )
    await publish_domain_event(
        event_type,
        payload.model_dump(mode="json"),
        company_id=entity.company_id,
        actor_user_id=entity.user_id,
    )

"""
Сборка ``EntityResponse`` с вычисляемыми полями (семантический статус индекса, work_item_id).
"""

from __future__ import annotations

from collections.abc import Sequence

from apps.crm.db.models import CRMEntity
from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.crm.models.api import EntityResponse
from apps.crm.services.crm_work_item_service import CrmWorkItemService


async def build_entity_responses_with_semantic_index(
    entity_repo: EntityRepository,
    entities: Sequence[CRMEntity],
    *,
    crm_work_item_service: CrmWorkItemService | None = None,
) -> list[EntityResponse]:
    """Один batch-запрос к vector_documents на весь список сущностей."""
    entities_list = list(entities)
    if not entities_list:
        return []
    status_by_id = await entity_repo.batch_semantic_text_index_status(entities_list)
    work_item_id_by_entity: dict[str, str] = {}
    if crm_work_item_service is not None:
        task_entity_ids = [
            ent.entity_id for ent in entities_list if ent.entity_type == "task"
        ]
        if task_entity_ids:
            company_id = entities_list[0].company_id
            work_item_id_by_entity = await crm_work_item_service.map_work_item_ids_by_entities(
                company_id=company_id,
                entity_ids=task_entity_ids,
            )
    return [
        EntityResponse.model_validate(ent).model_copy(
            update={
                "semantic_text_index_status": status_by_id.get(ent.entity_id),
                "work_item_id": work_item_id_by_entity.get(ent.entity_id),
            },
        )
        for ent in entities_list
    ]

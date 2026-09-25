"""
Сборка ``EntityResponse`` с вычисляемыми полями (семантический статус индекса, work_item_id).
"""

from __future__ import annotations

from collections.abc import Sequence

from apps.crm.models.api import EntityResponse, SemanticTextIndexStatus
from apps.crm.models.crm_entity import CRMEntity, entity_namespace
from apps.crm.services.crm_work_item_service import CrmWorkItemService
from core.rag import BaseRAGProvider
from core.rag.providers.pgvector_provider import PgVectorProvider


async def semantic_text_index_status_by_entity(
    rag: BaseRAGProvider,
    entities: list[CRMEntity],
) -> dict[str, SemanticTextIndexStatus | None]:
    if len(entities) == 0:
        return {}
    if not isinstance(rag, PgVectorProvider):
        return {row.entity_id: None for row in entities}
    triples: list[tuple[str, str, str]] = []
    for row in entities:
        triples.append((entity_namespace(row), row.entity_id.strip(), row.company_id.strip()))
    triple_status = await rag.batch_document_semantic_index_status(triples)
    result: dict[str, SemanticTextIndexStatus | None] = {}
    for row in entities:
        key = (entity_namespace(row), row.entity_id.strip(), row.company_id.strip())
        result[row.entity_id] = triple_status[key]
    return result


async def build_entity_responses_with_semantic_index(
    rag: BaseRAGProvider,
    entities: Sequence[CRMEntity],
    *,
    crm_work_item_service: CrmWorkItemService | None = None,
) -> list[EntityResponse]:
    """Один batch-запрос к vector_documents на весь список сущностей."""
    entities_list = list(entities)
    if len(entities_list) == 0:
        return []
    status_by_id = await semantic_text_index_status_by_entity(rag, entities_list)
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

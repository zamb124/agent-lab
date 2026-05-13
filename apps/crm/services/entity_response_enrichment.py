"""
Сборка ``EntityResponse`` с вычисляемыми полями (семантический статус индекса).
"""

from __future__ import annotations

from collections.abc import Sequence

from apps.crm.db.models import CRMEntity
from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.crm.models.api import EntityResponse


async def build_entity_responses_with_semantic_index(
    entity_repo: EntityRepository,
    entities: Sequence[CRMEntity],
) -> list[EntityResponse]:
    """Один batch-запрос к vector_documents на весь список сущностей."""
    entities_list = list(entities)
    if not entities_list:
        return []
    status_by_id = await entity_repo.batch_semantic_text_index_status(entities_list)
    return [
        EntityResponse.model_validate(ent).model_copy(
            update={"semantic_text_index_status": status_by_id.get(ent.entity_id)},
        )
        for ent in entities_list
    ]

"""
Сводка CRM namespace для ассистента Lara (счётчики без выборки всех строк).
"""

from __future__ import annotations

from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.crm.db.repositories.task_repository import TaskRepository
from apps.crm.models.api import LaraNamespaceSummaryResponse


class LaraNamespaceService:
    def __init__(
        self,
        task_repo: TaskRepository,
        entity_repo: EntityRepository,
    ) -> None:
        self._task_repo: TaskRepository = task_repo
        self._entity_repo: EntityRepository = entity_repo

    async def get_summary(self, namespace: str) -> LaraNamespaceSummaryResponse:
        ns = namespace.strip()
        if not ns:
            raise ValueError("namespace is required")

        awaiting = await self._task_repo.count_awaiting_review_for_namespace(ns)
        in_progress = await self._task_repo.count_in_progress_for_namespace(
            ns, task_type="knowledge_import"
        )
        notes_draft = await self._entity_repo.count_notes_with_analysis_draft_not_applied(ns)

        return LaraNamespaceSummaryResponse(
            namespace=ns,
            knowledge_imports_awaiting_review=awaiting,
            knowledge_imports_in_progress=in_progress,
            notes_with_analysis_draft_not_applied=notes_draft,
        )

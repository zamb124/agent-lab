"""
Сводка рабочего пространства CRM для ассистента Lara (счётчики без выборки всех строк).
"""

from __future__ import annotations

from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.crm.db.repositories.knowledge_import_repository import KnowledgeImportRepository
from apps.crm.models.api import LaraWorkspaceSummaryResponse


class LaraWorkspaceService:
    def __init__(
        self,
        import_repo: KnowledgeImportRepository,
        entity_repo: EntityRepository,
    ) -> None:
        self._import_repo = import_repo
        self._entity_repo = entity_repo

    async def get_lara_summary(self, namespace: str) -> LaraWorkspaceSummaryResponse:
        ns = namespace.strip()
        if not ns:
            raise ValueError("namespace is required")

        awaiting = await self._import_repo.count_imports_awaiting_review_for_namespace(ns)
        in_progress = await self._import_repo.count_imports_in_progress_for_namespace(ns)
        notes_draft = await self._entity_repo.count_notes_with_analysis_draft_not_applied(ns)

        return LaraWorkspaceSummaryResponse(
            namespace=ns,
            knowledge_imports_awaiting_review=awaiting,
            knowledge_imports_in_progress=in_progress,
            notes_with_analysis_draft_not_applied=notes_draft,
        )

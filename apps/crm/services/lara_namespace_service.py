"""
Сводка CRM namespace для ассистента Lara (счётчики без выборки всех строк).
"""

from __future__ import annotations

from apps.crm.models.api import LaraNamespaceSummaryResponse
from apps.crm.models.crm_entity import CRMEntity
from apps.crm.models.task import CRMTask
from core.context import require_active_company


class LaraNamespaceService:
    async def get_summary(self, namespace: str) -> LaraNamespaceSummaryResponse:
        ns = namespace.strip()
        if not ns:
            raise ValueError("namespace is required")

        company_id = require_active_company().company_id
        awaiting = await CRMTask.count_knowledge_import_awaiting_review(
            ns, company_id=company_id
        )
        in_progress = await CRMTask.count_knowledge_import_in_progress(
            ns, company_id=company_id
        )
        notes_draft = await CRMEntity.count_notes_with_analysis_draft_not_applied(ns)

        return LaraNamespaceSummaryResponse(
            namespace=ns,
            knowledge_imports_awaiting_review=awaiting,
            knowledge_imports_in_progress=in_progress,
            notes_with_analysis_draft_not_applied=notes_draft,
        )

"""`op_*` консоли Frontend: один handler на verb, REST и WS RPC зовут одну функцию."""

from __future__ import annotations

from pydantic import Field

from apps.frontend.container import FrontendContainer
from core.ai.providers import PROVIDER_LITSERVE
from core.models import StrictBaseModel
from core.models.identity_models import SYSTEM_COMPANY_ID, User
from core.request_scope import require_company


class FrontendEmptyPayload(StrictBaseModel):
    pass


class DashboardStats(StrictBaseModel):
    """Счётчики витрины /dashboard: одна команда вместо запросов в каждый сервис."""

    flows_total: int = Field(ge=0)
    namespaces_total: int = Field(ge=0, description="Platform Namespace компании — пространства CRM и Sync")
    rag_namespaces_total: int = Field(ge=0)
    documents_files_total: int = Field(ge=0)
    litserve_models_total: int | None = Field(default=None, description="Только для компании system")


async def op_dashboard_stats(
    payload: FrontendEmptyPayload, *, user: User, container: FrontendContainer
) -> DashboardStats:
    _ = payload, user
    scope = require_company()
    flow_index = await container.flows_flow_repository.list_index()
    rag_namespaces = await container.rag_repository.list_namespaces()
    documents_total = 0
    if container.authz_explorer_repositories.office_binding is not None:
        documents_total = await container.authz_explorer_repositories.office_binding.count_active_in_company(
            scope.company_id
        )
    litserve_total: int | None = None
    if scope.company_id == SYSTEM_COMPANY_ID:
        litserve_total = len(await container.ai_model_catalog_repository.list_by_provider(PROVIDER_LITSERVE))
    return DashboardStats(
        flows_total=len(flow_index),
        namespaces_total=await container.namespace_service.count(),
        rag_namespaces_total=len(rag_namespaces),
        documents_files_total=documents_total,
        litserve_models_total=litserve_total,
    )

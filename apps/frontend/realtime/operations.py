"""`op_*` консоли Frontend: один handler на verb, REST и WS RPC зовут одну функцию."""

from __future__ import annotations

from pydantic import Field

from apps.flows.src.models.flow_config import FlowConfig
from apps.frontend.di import Di
from apps.office.db.models import OfficeDocumentBinding
from core.ai.models import AIModelRecord
from core.ai.providers import PROVIDER_LITSERVE
from core.models import StrictBaseModel
from core.models.identity_models import SYSTEM_COMPANY_ID, User
from core.rag.constants import RAG_IN_PROCESS_PROVIDER_ID
from core.rag.factory import get_rag_provider
from core.request_scope import require_company
from core.websocket import EmptyPayload


class DashboardStats(StrictBaseModel):
    """Счётчики витрины /dashboard: одна команда вместо запросов в каждый сервис."""

    flows_total: int = Field(ge=0)
    namespaces_total: int = Field(ge=0, description="Platform Namespace компании — пространства CRM и Sync")
    rag_namespaces_total: int = Field(ge=0)
    documents_files_total: int = Field(ge=0)
    litserve_models_total: int | None = Field(default=None, description="Только для компании system")


async def op_dashboard_stats(
    payload: EmptyPayload, *, user: User, di: Di
) -> DashboardStats:
    _ = payload, user
    scope = require_company()
    flow_index = await FlowConfig.list_index()
    rag_namespaces = await get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID).list_namespaces()
    documents_total = await OfficeDocumentBinding.count_alive_bindings(scope.company_id)
    litserve_total: int | None = None
    if scope.company_id == SYSTEM_COMPANY_ID:
        litserve_total = len(await AIModelRecord.list_by_provider(PROVIDER_LITSERVE))
    return DashboardStats(
        flows_total=len(flow_index),
        namespaces_total=await di.namespace_service.count(),
        rag_namespaces_total=len(rag_namespaces),
        documents_files_total=documents_total,
        litserve_models_total=litserve_total,
    )

"""DI процесса crm."""

from typing import Annotated

from apps.crm.config import CRMSettings
from apps.crm.integrations.amocrm.connector import AmoCRMConnector
from apps.crm.integrations.registry import IntegrationRegistry
from apps.crm.services.access_grant_service import AccessGrantService
from apps.crm.services.access_request_service import AccessRequestService
from apps.crm.services.attachment_service import AttachmentService
from apps.crm.services.company_init_service import CompanyInitService
from apps.crm.services.crm_entity_access_service import CrmEntityAccessService
from apps.crm.services.crm_work_item_service import CrmWorkItemService
from apps.crm.services.entity_service import EntityService
from apps.crm.services.graph_service import GraphService
from apps.crm.services.integration_auto_sync_service import IntegrationAutoSyncService
from apps.crm.services.lara_namespace_service import LaraNamespaceService
from apps.crm.services.namespace_template_service import NamespaceTemplateService
from apps.crm.services.suggest_service import SuggestService
from apps.crm.services.task_service import TaskService
from apps.crm.services.user_person_service import UserPersonService
from core.authz.service import AuthzService
from core.clients.a2a_client import A2AClient
from core.clients.redis_client import RedisClient
from core.clients.scheduler_client import SchedulerClient
from core.clients.service_client import ServiceClient
from core.db.storage import SharedStorage
from core.di import http_di, recipe, task_di
from core.di.platform import PlatformDi
from core.identity.integration_external_author import IntegrationExternalAuthorService
from core.integrations.oauth_service import OAuthService
from core.namespace import NamespaceService
from core.rag.base_provider import BaseRAGProvider
from core.rag.constants import RAG_IN_PROCESS_PROVIDER_ID
from core.rag.factory import get_rag_provider
from core.rag.post_retrieval_rerank import RerankScoreCache
from core.worktracker.access_service import WorkQueueAccessService
from core.worktracker.queue_access import WorkQueueAccessPort


@recipe
def crm_rag_provider() -> BaseRAGProvider:
    return get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID)


@recipe
def rerank_score_cache(redis_client: RedisClient) -> RerankScoreCache:
    return RerankScoreCache(redis_client)


@recipe
def crm_a2a_client(settings: CRMSettings) -> A2AClient:
    return A2AClient(timeout=settings.analysis_a2a_timeout_seconds)


@recipe
def scheduler_client(service_client: ServiceClient) -> SchedulerClient:
    return SchedulerClient(service_client=service_client)


@recipe
def work_queue_access(authz_service: AuthzService) -> WorkQueueAccessPort:
    return WorkQueueAccessService(authz_service)


@recipe
def integration_external_author_service(
    storage: SharedStorage,
    authz_service: AuthzService,
) -> IntegrationExternalAuthorService:
    return IntegrationExternalAuthorService(storage=storage, authz=authz_service)


@recipe
def integration_registry(
    oauth_service: OAuthService,
    crm_rag_provider: BaseRAGProvider,
    entity_service: EntityService,
    namespace_service: NamespaceService,
    task_service: TaskService,
    integration_external_author_service: IntegrationExternalAuthorService,
    namespace_template_service: NamespaceTemplateService,
    crm_entity_access_service: CrmEntityAccessService,
) -> IntegrationRegistry:
    return IntegrationRegistry(
        [
            AmoCRMConnector(
                oauth_service=oauth_service,
                rag=crm_rag_provider,
                entity_service=entity_service,
                namespace_service=namespace_service,
                task_service=task_service,
                integration_external_author=integration_external_author_service,
                namespace_template_service=namespace_template_service,
                entity_access=crm_entity_access_service,
            )
        ]
    )


CRM_RECIPES = (
    crm_rag_provider,
    rerank_score_cache,
    crm_a2a_client,
    scheduler_client,
    work_queue_access,
    integration_external_author_service,
    integration_registry,
)

class CrmDi(PlatformDi, recipes=CRM_RECIPES):
    access_grant_service: AccessGrantService
    access_request_service: AccessRequestService
    attachment_service: AttachmentService
    company_init_service: CompanyInitService
    crm_entity_access_service: CrmEntityAccessService
    crm_work_item_service: CrmWorkItemService
    entity_service: EntityService
    graph_service: GraphService
    integration_auto_sync_service: IntegrationAutoSyncService
    integration_registry: IntegrationRegistry
    lara_namespace_service: LaraNamespaceService
    namespace_template_service: NamespaceTemplateService
    suggest_service: SuggestService
    task_service: TaskService
    user_person_service: UserPersonService


Di = Annotated[CrmDi, http_di(CrmDi), task_di(CrmDi)]

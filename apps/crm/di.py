"""DI процесса crm."""

from typing import Annotated

from apps.crm.components import CRM_RECIPES
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
from core.di import http_di, task_di
from core.di.platform import PlatformDi


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

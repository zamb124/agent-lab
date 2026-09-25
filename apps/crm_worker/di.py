"""DI процесса crm_worker: задачи анализа, импорта и синхронизации интеграций."""

from typing import Annotated

from apps.crm.components import CRM_RECIPES
from apps.crm.integrations.registry import IntegrationRegistry
from apps.crm.services.entity_service import EntityService
from apps.crm.services.note_processing_service import NoteProcessingService
from apps.crm.services.suggest_service import SuggestService
from core.di import http_di, task_di
from core.di.platform import PlatformDi


class CrmWorkerDi(PlatformDi, recipes=CRM_RECIPES):
    entity_service: EntityService
    integration_registry: IntegrationRegistry
    note_processing_service: NoteProcessingService
    suggest_service: SuggestService


Di = Annotated[CrmWorkerDi, http_di(CrmWorkerDi), task_di(CrmWorkerDi)]

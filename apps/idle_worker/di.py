"""DI idle_worker: очереди ``idle`` и ``a2a_push``."""

from typing import Annotated

from core.ai.llm_models_service import LLMModelsService
from core.clients.scheduler_client import SchedulerClient
from core.clients.service_client import ServiceClient
from core.db.storage import SharedStorage
from core.di import recipe
from core.di.boundary import http_di, task_di
from core.di.platform import PlatformDi
from core.files.purge import FilePurgeService
from core.short_links import ShortLinkService


@recipe
def scheduler_client(service_client: ServiceClient) -> SchedulerClient:
    return SchedulerClient(service_client=service_client)


class IdleWorkerDi(PlatformDi, recipes=(scheduler_client,)):
    file_purge_service: FilePurgeService
    llm_models_service: LLMModelsService
    service_client: ServiceClient
    shared_storage: SharedStorage
    short_link_service: ShortLinkService


Di = Annotated[IdleWorkerDi, http_di(IdleWorkerDi), task_di(IdleWorkerDi)]

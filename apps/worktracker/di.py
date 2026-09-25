"""DI процесса worktracker: ядро задач WorkItem."""

from typing import Annotated

from core.authz.service import AuthzService
from core.di import http_di, recipe, task_di
from core.di.platform import PlatformDi
from core.worktracker.access_service import WorkQueueAccessService
from core.worktracker.queue_access import WorkQueueAccessPort
from core.worktracker.service import WorkItemService


@recipe
def work_queue_access(authz_service: AuthzService) -> WorkQueueAccessPort:
    return WorkQueueAccessService(authz_service)


class WorktrackerDi(PlatformDi, recipes=(work_queue_access,)):
    work_item_service: WorkItemService


Di = Annotated[WorktrackerDi, http_di(WorktrackerDi), task_di(WorktrackerDi)]

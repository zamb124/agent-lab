"""DI CLI backfill устройств LinnexAgent: shared storage и OpenFGA."""

from typing import Annotated

from core.authz.service import AuthzService
from core.db.storage import SharedStorage
from core.di import ServiceDi, http_di, task_di
from core.di.platform import authz_service, shared_storage


class AgentDi(ServiceDi, recipes=(shared_storage, authz_service)):
    authz_service: AuthzService
    shared_storage: SharedStorage


Di = Annotated[AgentDi, http_di(AgentDi), task_di(AgentDi)]

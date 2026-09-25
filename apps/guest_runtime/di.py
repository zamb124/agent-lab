"""DI процесса guest_runtime: ферма code_agent."""

from typing import Annotated

from apps.guest_runtime.services.farm_service import GuestFarmService
from core.clients.files_client import FilesClient
from core.di import http_di, recipe, task_di
from core.di.platform import PlatformDi


@recipe
def files_client() -> FilesClient:
    return FilesClient(service="office")


class GuestRuntimeDi(PlatformDi, recipes=(files_client,)):
    farm_service: GuestFarmService


Di = Annotated[GuestRuntimeDi, http_di(GuestRuntimeDi), task_di(GuestRuntimeDi)]

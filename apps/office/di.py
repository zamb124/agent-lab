"""DI процесса office: документы, каталоги и viewer."""

from typing import Annotated

from apps.office.services.catalog_rag_index_service import OfficeCatalogRagIndexService
from apps.office.services.docs_placement_service import DocsPlacementService
from apps.office.services.office_access_service import OfficeAccessService
from apps.office.services.viewer_service import DocumentViewerService
from core.clients.service_client import ServiceClient
from core.data_tables.service import DataTableService
from core.di import http_di, task_di
from core.di.platform import PlatformDi


class OfficeDi(PlatformDi):
    catalog_rag_index_service: OfficeCatalogRagIndexService
    data_table_service: DataTableService
    docs_placement_service: DocsPlacementService
    office_access_service: OfficeAccessService
    service_client: ServiceClient
    viewer_service: DocumentViewerService


Di = Annotated[OfficeDi, http_di(OfficeDi), task_di(OfficeDi)]

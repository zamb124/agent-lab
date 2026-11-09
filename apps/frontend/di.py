"""DI процесса frontend: консоль компании, публичный сайт и биллинг."""

from typing import Annotated

from apps.frontend.services.authz_explorer_service import AuthzExplorerService
from apps.frontend.services.cookie_consent_service import CookieConsentService
from apps.frontend.services.seo_snapshot_service import SeoSnapshotService
from core.clients.browser_fetch_client import BrowserFetchClient
from core.clients.service_client import ServiceClient
from core.db.storage import SharedStorage
from core.di import http_di, recipe, task_di
from core.di.platform import PlatformDi
from core.files.company_storage_service import CompanyStorageService
from core.payments import PaymentService
from core.short_links.service import ShortLinkService


@recipe
def payment_service(storage: SharedStorage) -> PaymentService:
    return PaymentService(storage=storage)


class FrontendDi(PlatformDi, recipes=(payment_service,)):
    authz_explorer_service: AuthzExplorerService
    browser_fetch_client: BrowserFetchClient
    cookie_consent_service: CookieConsentService
    company_storage_service: CompanyStorageService
    payment_service: PaymentService
    seo_snapshot_service: SeoSnapshotService
    service_client: ServiceClient
    shared_storage: SharedStorage
    short_link_service: ShortLinkService


Di = Annotated[FrontendDi, http_di(FrontendDi), task_di(FrontendDi)]

"""Платформенный DI: компоненты core-роутеров, AuthMiddleware и lifecycle сервиса.

Сервис с платформенными роутерами или AuthMiddleware наследует ``PlatformDi``;
core-код получает эти компоненты через ``Di`` этого модуля.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from core.authz.factory import build_authz_service
from core.authz.service import AuthzService
from core.billing.service import BillingService
from core.calendar.service import CalendarService
from core.catalog.service import CatalogService
from core.clients.geocoding.base import Geocoder
from core.clients.geocoding.nominatim import NominatimGeocoder
from core.clients.rag_client import RagClient
from core.clients.redis_client import RedisClient
from core.clients.service_client import ServiceClient
from core.config.models import (
    BillingConfig,
    CustomerAuthConfig,
    DatabaseConfig,
    GeocodingConfig,
    MailConfig,
    MailSyncConfig,
    OpenFGAConfig,
    ServerConfig,
)
from core.context import get_context
from core.customers.address_service import CustomerAddressService
from core.customers.auth_service import CustomerAuthService
from core.customers.notify_service import CustomerNotifyService
from core.customers.service import CustomerService
from core.customers.session import CustomerSessionService
from core.db.storage import SharedStorage, Storage
from core.di.boundary import http_di, task_di
from core.di.kit import ProcessIdentity, ServiceDi, recipe
from core.documents.tree_service import DocumentTreeService
from core.files.chunked_upload import ChunkedUploadService
from core.files.hooks import index_file_in_rag
from core.files.image_variants.service import ImageVariantService
from core.files.service import FilesService
from core.identity.auth_service import AuthService
from core.identity.badge_service import BadgeService
from core.integrations.company_credentials import CompanyIntegrationCredentialService
from core.integrations.oauth_service import OAuthService
from core.mail.attachment_index import MailAttachmentFileIndex
from core.mail.service import MailService
from core.models.billing_models import TariffPlan
from core.namespace import NamespaceService


@recipe
async def redis_client(database: DatabaseConfig) -> AsyncIterator[RedisClient]:
    """Один Redis-клиент процесса; соединение открывается при первом запросе."""
    if database.redis_url.strip() == "":
        raise ValueError("database.redis_url is required")
    client = RedisClient(database.redis_url)
    yield client
    await client.close()


@recipe
def shared_storage(database: DatabaseConfig) -> SharedStorage:
    return SharedStorage(Storage(db_url=database.shared_url, get_context_func=get_context))


@recipe
async def authz_service(openfga: OpenFGAConfig) -> AsyncIterator[AuthzService]:
    # Клиент openfga-sdk держит aiohttp-сессию — без close до GC печатает
    # "Unclosed connector" в каждом процессе.
    service = build_authz_service(openfga)
    yield service
    await service.close()


@recipe
def billing_service(billing: BillingConfig, storage: SharedStorage) -> BillingService:
    return BillingService(
        tariff_prices={TariffPlan(plan): tree for plan, tree in billing.tariff_prices.items()},
        resource_base_prices=billing.resource_base_prices,
        shared_storage=storage,
        balance_enforcement_enabled=billing.balance_enforcement_enabled,
        balance_enforcement_exempt_company_ids=list(billing.balance_enforcement_exempt_company_ids),
    )


@recipe
def customer_service() -> CustomerService:
    return CustomerService()


@recipe
def customer_session_service() -> CustomerSessionService:
    return CustomerSessionService()


@recipe
def customer_auth_service(
    customer_auth: CustomerAuthConfig,
    server: ServerConfig,
    redis_client: RedisClient,
    customer_service: CustomerService,
    customer_session_service: CustomerSessionService,
) -> CustomerAuthService:
    return CustomerAuthService(
        cfg=customer_auth,
        env=server.env,
        redis=redis_client,
        customers=customer_service,
        sessions=customer_session_service,
    )


@recipe
def customer_notify_service(
    customer_auth: CustomerAuthConfig,
    server: ServerConfig,
    redis_client: RedisClient,
) -> CustomerNotifyService:
    return CustomerNotifyService(
        cfg=customer_auth,
        env=server.env,
        redis=redis_client,
    )


@recipe
def geocoder(geocoding: GeocodingConfig, redis_client: RedisClient) -> Geocoder:
    return NominatimGeocoder(geocoding, redis_client)


@recipe
def customer_address_service(geocoder: Geocoder) -> CustomerAddressService:
    return CustomerAddressService(geocoder)


@recipe
def files_service(identity: ProcessIdentity, document_tree_service: DocumentTreeService) -> FilesService:
    return FilesService(
        tree=document_tree_service,
        rag_index_hook=index_file_in_rag,
        files_route_segment=identity.files_route_segment,
    )


@recipe
def chunked_upload_service(
    identity: ProcessIdentity, document_tree_service: DocumentTreeService
) -> ChunkedUploadService:
    return ChunkedUploadService(
        tree=document_tree_service,
        rag_index_hook=index_file_in_rag,
        files_route_segment=identity.files_route_segment,
    )


@recipe
def mail_service(
    mail: MailConfig,
    mail_sync: MailSyncConfig,
    authz_service: AuthzService,
    namespace_service: NamespaceService,
    files_service: FilesService,
    attachment_file_index: MailAttachmentFileIndex,
    calendar_service: CalendarService,
    service_client: ServiceClient,
) -> MailService:
    return MailService(
        authz=authz_service,
        namespace_service=namespace_service,
        rag_client=RagClient(http=service_client),
        mail_config=mail,
        files_service=files_service,
        attachment_file_index=attachment_file_index,
        mail_sync_backfill_batch_size=mail_sync.backfill_batch_size,
        mail_sync_reconcile_every_n=mail_sync.reconcile_every_n_syncs,
        calendar_bridge=calendar_service,
    )


class PlatformDi(
    ServiceDi,
    recipes=(
        redis_client,
        shared_storage,
        authz_service,
        billing_service,
        files_service,
        chunked_upload_service,
        mail_service,
        customer_service,
        customer_session_service,
        customer_auth_service,
        customer_notify_service,
        geocoder,
        customer_address_service,
    ),
):
    auth_service: AuthService
    authz_service: AuthzService
    badge_service: BadgeService
    billing_service: BillingService
    calendar_service: CalendarService
    catalog_service: CatalogService
    chunked_upload_service: ChunkedUploadService
    company_integration_credential_service: CompanyIntegrationCredentialService
    customer_address_service: CustomerAddressService
    customer_auth_service: CustomerAuthService
    customer_notify_service: CustomerNotifyService
    customer_service: CustomerService
    customer_session_service: CustomerSessionService
    geocoder: Geocoder
    image_variant_service: ImageVariantService
    service_client: ServiceClient
    document_tree_service: DocumentTreeService
    files_service: FilesService
    mail_service: MailService
    namespace_service: NamespaceService
    oauth_service: OAuthService
    redis_client: RedisClient


Di = Annotated[PlatformDi, http_di(PlatformDi), task_di(PlatformDi)]

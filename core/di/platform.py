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
from core.clients.rag_client import RagClient
from core.clients.redis_client import RedisClient
from core.clients.service_client import ServiceClient
from core.config.models import (
    BillingConfig,
    DatabaseConfig,
    MailConfig,
    MailSyncConfig,
    OpenFGAConfig,
)
from core.context import get_context
from core.db.storage import SharedStorage, Storage
from core.di.boundary import http_di, task_di
from core.di.kit import ProcessIdentity, ServiceDi, recipe
from core.files.chunked_upload import ChunkedUploadService
from core.files.hooks import bind_document_placement, index_file_in_rag
from core.files.service import FilesService
from core.identity.auth_service import AuthService
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
def authz_service(openfga: OpenFGAConfig) -> AuthzService:
    return build_authz_service(openfga)


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
def files_service(identity: ProcessIdentity) -> FilesService:
    return FilesService(
        docs_bind_hook=bind_document_placement,
        rag_index_hook=index_file_in_rag,
        files_route_segment=identity.files_route_segment,
    )


@recipe
def chunked_upload_service(identity: ProcessIdentity) -> ChunkedUploadService:
    return ChunkedUploadService(
        docs_bind_hook=bind_document_placement,
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
    ),
):
    auth_service: AuthService
    authz_service: AuthzService
    billing_service: BillingService
    calendar_service: CalendarService
    chunked_upload_service: ChunkedUploadService
    company_integration_credential_service: CompanyIntegrationCredentialService
    files_service: FilesService
    mail_service: MailService
    namespace_service: NamespaceService
    oauth_service: OAuthService
    redis_client: RedisClient


Di = Annotated[PlatformDi, http_di(PlatformDi), task_di(PlatformDi)]

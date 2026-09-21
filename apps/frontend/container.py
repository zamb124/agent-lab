"""
Dependency Injection контейнер для Frontend
"""

from apps.crm.db.base import CRMDatabase
from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.flows.src.db.flow_repository import FlowRepository
from apps.frontend.services.authz_explorer_hydrate import (
    AuthzExplorerHydrator,
    AuthzExplorerRepositories,
)
from apps.frontend.services.authz_explorer_service import AuthzExplorerService
from apps.frontend.services.cookie_consent_repository import CookieConsentRepository
from apps.frontend.services.cookie_consent_service import CookieConsentService
from apps.office.db.base import OfficeDatabase
from apps.office.db.repositories.catalog_repository import CatalogRepository
from apps.office.db.repositories.document_binding_repository import DocumentBindingRepository
from apps.sync.db.base import SyncDatabase
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.wiki.db.base import WikiDatabase
from apps.wiki.db.repositories.wiki_repository import WikiRepository
from core.clients.rag_client import RagClient
from core.config import get_settings
from core.container import BaseContainer, ContainerRegistry, lazy
from core.context import get_context
from core.db.repositories.embed_config_repository import EmbedConfigRepository
from core.db.repositories.embed_mapping_repository import EmbedMappingRepository
from core.db.storage import Storage
from core.logging import get_logger
from core.payments import PaymentService
from core.rag.post_retrieval_rerank import RerankScoreCache
from core.worktracker.db import WorktrackerDatabase
from core.worktracker.repository import WorktrackerRepository

logger = get_logger(__name__)


class FrontendContainer(BaseContainer):
    """Контейнер зависимостей для Frontend"""

    @lazy
    def embed_config_repository(self) -> EmbedConfigRepository:
        """Репозиторий для конфигураций встраиваемых виджетов"""
        return EmbedConfigRepository(storage=self.shared_storage)

    @lazy
    def embed_mapping_repository(self) -> EmbedMappingRepository:
        """Репозиторий для глобального маппинга embed_id -> company_id"""
        return EmbedMappingRepository(storage=self.shared_storage)

    @lazy
    def payment_service(self) -> PaymentService:
        return PaymentService(
            company_repository=self.company_repository,
            storage=self.shared_storage,
        )

    @lazy
    def flows_storage(self) -> Storage:
        """
        Storage над БД сервиса flows.

        Frontend имеет approved cross-service доступ к flows-БД для read-only
        landing-сценариев (architecture.mdc: "Если у процесса есть доступ к
        БД peer-домена — данные через репозиторий"). Это явный @lazy, чтобы
        не пересобирать Storage в каждом @lazy-репозитории и не нарушать DRY.

        Если `database.flows_url` не задан — старт сервиса падает: zero-guess.
        """
        url = get_settings().database.flows_url
        if not url:
            raise ValueError(
                "database.flows_url is required for FrontendContainer.flows_storage: "
                + "frontend reads flow configs directly from the flows DB for landing pages"
            )
        return Storage(db_url=url, get_context_func=get_context)

    @lazy
    def flows_flow_repository(self) -> FlowRepository:
        """Репозиторий flows из сервисной БД flows (read-only сценарии без HTTP к peers)."""
        return FlowRepository(storage=self.flows_storage)

    @lazy
    def authz_explorer_repositories(self) -> AuthzExplorerRepositories:
        """Репозитории владельцев для Access Explorer; домен без URL БД гидрируется как unavailable."""
        database = get_settings().database
        return AuthzExplorerRepositories(
            flow=self.flows_flow_repository,
            mailbox_binding=self.mailbox_binding_repository,
            worktracker=(
                WorktrackerRepository(WorktrackerDatabase(database.worktracker_url))
                if database.worktracker_url
                else None
            ),
            wiki=WikiRepository(WikiDatabase(database.wiki_url)) if database.wiki_url else None,
            crm_entity=(
                EntityRepository(
                    CRMDatabase.get_instance(database.crm_url),
                    rag_repository=self.rag_repository,
                    rerank_score_cache=RerankScoreCache(self.redis_client),
                )
                if database.crm_url
                else None
            ),
            office_catalog=(
                CatalogRepository(OfficeDatabase.get_instance(database.office_url)) if database.office_url else None
            ),
            office_binding=(
                DocumentBindingRepository(OfficeDatabase.get_instance(database.office_url))
                if database.office_url
                else None
            ),
            sync_channel=(
                ChannelRepository(SyncDatabase.get_instance(database.sync_url)) if database.sync_url else None
            ),
        )

    @lazy
    def authz_explorer_hydrator(self) -> AuthzExplorerHydrator:
        return AuthzExplorerHydrator(self.authz_explorer_repositories)

    @lazy
    def authz_explorer_service(self) -> AuthzExplorerService:
        return AuthzExplorerService(
            authz=self.authz_service,
            hydrator=self.authz_explorer_hydrator,
        )

    @lazy
    def rag_client(self) -> RagClient:
        return RagClient(self.service_client)

    @lazy
    def cookie_consent_repository(self) -> CookieConsentRepository:
        return CookieConsentRepository(db_url=self.required_shared_db_url)

    @lazy
    def cookie_consent_service(self) -> CookieConsentService:
        return CookieConsentService(repository=self.cookie_consent_repository)


def _create_frontend_container() -> FrontendContainer:
    settings = get_settings()
    if not settings.database.shared_url:
        raise ValueError("database.shared_url is not set")
    return FrontendContainer(
        db_url=settings.database.shared_url,
        shared_db_url=settings.database.shared_url,
    )


_frontend_registry: ContainerRegistry[FrontendContainer] = ContainerRegistry(
    _create_frontend_container, name="FrontendContainer"
)

get_frontend_container = _frontend_registry.get
set_frontend_container = _frontend_registry.set
reset_frontend_container = _frontend_registry.reset
get_container = _frontend_registry.get

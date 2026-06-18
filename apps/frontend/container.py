"""
Dependency Injection контейнер для Frontend
"""

from apps.flows.src.db.flow_repository import FlowRepository
from apps.search.db.base import SearchDatabase
from apps.search.db.crawl_repositories import (
    CrawlDomainRepository,
    CrawlJobRepository,
    CrawlProfileRepository,
    CrawlUrlRepository,
)
from apps.search.services.crawl.report_service import CrawlReportService
from core.clients.rag_client import RagClient
from core.clients.redis_client import RedisClient
from core.clients.search_client import SearchClient
from core.config import get_settings
from core.container import BaseContainer, ContainerRegistry, lazy
from core.context import get_context
from core.db.repositories.embed_config_repository import EmbedConfigRepository
from core.db.repositories.embed_mapping_repository import EmbedMappingRepository
from core.db.storage import Storage
from core.logging import get_logger
from core.payments import PaymentService

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
                "database.flows_url обязателен для FrontendContainer.flows_storage: "
                + "frontend читает flow-конфиги напрямую из БД flows для landing-страниц"
            )
        return Storage(db_url=url, get_context_func=get_context)

    @lazy
    def flows_flow_repository(self) -> FlowRepository:
        """Репозиторий flows из сервисной БД flows (read-only сценарии без HTTP к peers)."""
        return FlowRepository(storage=self.flows_storage)

    @lazy
    def redis_client(self) -> RedisClient:
        return RedisClient(get_settings().database.redis_url)

    @lazy
    def search_database(self) -> SearchDatabase:
        url = get_settings().database.search_url
        if not url:
            raise ValueError(
                "database.search_url обязателен для crawl report: "
                + "frontend читает crawl state из platform_search"
            )
        return SearchDatabase.get_instance(url)

    @lazy
    def crawl_report_service(self) -> CrawlReportService:
        return CrawlReportService(
            crawl_profile_repository=CrawlProfileRepository(self.search_database),
            crawl_domain_repository=CrawlDomainRepository(self.search_database),
            crawl_url_repository=CrawlUrlRepository(self.search_database),
            crawl_job_repository=CrawlJobRepository(self.search_database),
            rag_client=self.rag_client,
        )

    @lazy
    def rag_client(self) -> RagClient:
        return RagClient(self.service_client)

    @lazy
    def search_client(self) -> SearchClient:
        return SearchClient(self.service_client)


def _create_frontend_container() -> FrontendContainer:
    settings = get_settings()
    if not settings.database.shared_url:
        raise ValueError("database.shared_url не задан")
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

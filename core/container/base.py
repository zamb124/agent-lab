"""
Базовый Dependency Injection Container с ленивой инициализацией.

Использование декоратора @lazy для сервисов:
    class MyContainer(BaseContainer):
        @lazy
        def my_service(self):
            return MyService(repository=self.my_repository)

Декоратор @lazy автоматически:
- Кэширует результат
- Превращает метод в property
- Добавляет логирование

ВАЖНО: BaseContainer НЕ зависит от app/* модулей!
"""

from collections.abc import Callable
from enum import Enum
from typing import (
    Generic,
    Never,
    Self,
    TypeVar,
    cast,
    overload,
)

from fastapi import APIRouter
from pydantic import BaseModel

from core.ai.model_catalog_repository import AIModelCatalogRepository
from core.api.crud_router import CRUDRouterGenerator
from core.billing import BillingService
from core.calendar.repositories import CalendarEventSqlRepository
from core.calendar.service import CalendarService
from core.clients.documents_client import DocumentsClient
from core.clients.rag_client import RagClient
from core.clients.scheduler_client import SchedulerClient
from core.clients.secrets_client import SecretsClient
from core.clients.service_client import ServiceClient
from core.config import get_settings
from core.context import get_context
from core.db.base_repository import BaseRepository
from core.db.repositories.api_key_repository import ApiKeyRepository
from core.db.repositories.auth_session_repository import AuthSessionRepository
from core.db.repositories.company_repository import CompanyRepository
from core.db.repositories.company_voice_provider_repository import CompanyVoiceProviderRepository
from core.db.repositories.llm_model_score_repository import LLMModelScoreRepository
from core.db.repositories.namespace_repository import NamespaceRepository
from core.db.repositories.pronunciation_rule_repository import (
    CompanyPronunciationRuleRepository,
    PlatformPronunciationRuleRepository,
)
from core.db.repositories.subdomain_repository import SubdomainRepository
from core.db.repositories.usage_repository import UsageRepository
from core.db.repositories.user_repository import UserRepository
from core.db.storage import Storage
from core.documents.placement import DocsBindResult, DocsPlacement
from core.files.file_repository import FileRepository
from core.files.purge import FilePurgeService
from core.files.s3_client import S3ClientFactory
from core.files.service import FilesService
from core.identity.auth_service import AuthService
from core.identity.integration_external_author import IntegrationExternalAuthorService
from core.integrations.oauth_service import OAuthService
from core.integrations.repository import IntegrationCredentialRepository
from core.logging import get_logger
from core.models.billing_models import TariffPlan
from core.push.repository import PushSubscriptionRepository
from core.rag.constants import RAG_IN_PROCESS_PROVIDER_ID
from core.rag.factory import get_rag_provider
from core.rag.llm_context_memory_store import RAGLLMContextMemoryStore
from core.rag.models import RAGMetadata
from core.rag.repository import RAGRepository
from core.short_links import ShortLinkService
from core.short_links.repository import ShortLinkRepository
from core.text_transforms import TextTransformService
from core.tracing.repository import SpanRepository
from core.variables.service import VariablesService

logger = get_logger(__name__)

class _LazyCacheState(Enum):
    UNSET = "unset"


_UNSET = _LazyCacheState.UNSET
_LazyT = TypeVar("_LazyT")
_LazyOwnerT = TypeVar("_LazyOwnerT")
_RepositoryModelT = TypeVar("_RepositoryModelT", bound=BaseModel)


class _LazyProperty(Generic[_LazyT]):
    _func: Callable[[Never], _LazyT]
    _attr_name: str
    __name__: str

    def __init__(self, func: Callable[[_LazyOwnerT], _LazyT]) -> None:
        self._func = cast(Callable[[Never], _LazyT], func)
        self._attr_name = f"_cached_{func.__name__}"
        self.__doc__ = func.__doc__
        self.__name__ = func.__name__
        self.__module__ = func.__module__

    @overload
    def __get__(
        self,
        instance: None,
        owner: type[_LazyOwnerT] | None = None,
    ) -> Self: ...

    @overload
    def __get__(
        self,
        instance: _LazyOwnerT,
        owner: type[_LazyOwnerT] | None = None,
    ) -> _LazyT: ...

    def __get__(
        self,
        instance: _LazyOwnerT | None,
        owner: type[_LazyOwnerT] | None = None,
    ) -> Self | _LazyT:
        _ = owner
        if instance is None:
            return self
        instance_dict = cast(dict[str, object], instance.__dict__)
        cached = instance_dict.get(self._attr_name, _UNSET)
        if cached is _UNSET:
            cached = self._func(cast(Never, instance))
            instance_dict[self._attr_name] = cached
            logger.debug(f"{self._func.__name__} инициализирован")
        return cast(_LazyT, cached)


def lazy(func: Callable[[_LazyOwnerT], _LazyT]) -> _LazyProperty[_LazyT]:
    """
    Декоратор для ленивой инициализации сервисов с кэшированием.

    Превращает метод в property с автоматическим кэшированием результата.

    Пример:
        class Container(BaseContainer):
            @lazy
            def my_service(self):
                return MyService(repo=self.repository)
    """
    return _LazyProperty(func)


class BaseContainer:
    """
    Базовый контейнер зависимостей с ленивой инициализацией.

    Содержит базовые сервисы:
    - storage, shared_storage: Storage для работы с БД
    - user_repository, company_repository, etc: Репозитории
    - auth_service: Сервис авторизации
    - variables_service: Сервис переменных

    Сервисы наследуют этот класс и добавляют свои зависимости через @lazy.
    """

    def __init__(
        self,
        db_url: str | None = None,
        shared_db_url: str | None = None,
    ) -> None:
        """
        Аргументы:
            db_url: URL service БД
            shared_db_url: URL shared БД для User, Company, Session
        """
        self.db_url: str | None = db_url
        if shared_db_url is None:
            settings = get_settings()
            shared_db_url = settings.database.shared_url
        self.shared_db_url: str | None = shared_db_url

        self._crud_routers: dict[str, APIRouter] = {}
        self._service_name: str | None = None

    @property
    def service_name(self) -> str:
        """
        Имя текущего сервиса из settings.server.name.
        Используется для определения локальный репозиторий или HTTP прокси.
        """
        if self._service_name is None:
            self._service_name = get_settings().server.name
        return self._service_name

    @property
    def required_shared_db_url(self) -> str:
        if not self.shared_db_url:
            raise ValueError("database.shared_url is required for shared platform repositories")
        return self.shared_db_url

    @property
    def required_db_url(self) -> str:
        if not self.db_url:
            raise ValueError("database service url is required for service repositories")
        return self.db_url

    # === Хранилище ===

    @lazy
    def storage(self) -> Storage:
        """Service Storage для работы с БД"""
        return Storage(db_url=self.db_url, get_context_func=get_context)

    @lazy
    def shared_storage(self) -> Storage:
        """Shared Storage для работы с общими данными (users, companies)"""
        return Storage(db_url=self.shared_db_url, get_context_func=get_context)

    @lazy
    def tracing_storage(self) -> Storage:
        """Storage только для platform_tracing (spans), не shared."""
        url = get_settings().database.tracing_url
        if not url:
            raise ValueError("DATABASE__TRACING_URL не задан в конфигурации")
        return Storage(db_url=url, get_context_func=get_context)

    # === Репозитории (shared БД) ===

    @lazy
    def user_repository(self) -> UserRepository:
        """UserRepository для работы с пользователями"""
        return UserRepository(storage=self.shared_storage)

    @lazy
    def company_repository(self) -> CompanyRepository:
        """CompanyRepository для работы с компаниями"""
        return CompanyRepository(storage=self.shared_storage)

    @lazy
    def auth_session_repository(self) -> AuthSessionRepository:
        """AuthSessionRepository для работы с сессиями авторизации"""
        return AuthSessionRepository(storage=self.shared_storage)

    @lazy
    def subdomain_repository(self) -> SubdomainRepository:
        """SubdomainRepository для работы с поддоменами"""
        return SubdomainRepository(storage=self.shared_storage)

    @lazy
    def secrets_client(self) -> SecretsClient:
        """SecretsClient для доступа к версионируемым переменным и секретам компании."""
        return SecretsClient(service_client=self.service_client)

    @lazy
    def usage_repository(self) -> UsageRepository:
        """UsageRepository для работы с использованием"""
        return UsageRepository(storage=self.shared_storage)

    @lazy
    def api_key_repository(self) -> ApiKeyRepository:
        """ApiKeyRepository для платформенных API-ключей компании."""
        return ApiKeyRepository(db_url=self.required_shared_db_url)

    @lazy
    def company_voice_provider_repository(self) -> CompanyVoiceProviderRepository:
        """Per-company override провайдеров речи (STT/TTS/VAD), shared БД."""
        return CompanyVoiceProviderRepository(db_url=self.required_shared_db_url)

    @lazy
    def platform_pronunciation_rule_repository(self) -> PlatformPronunciationRuleRepository:
        """Глобальные правила произношения TTS (system/superadmin), shared БД."""
        return PlatformPronunciationRuleRepository(db_url=self.required_shared_db_url)

    @lazy
    def company_pronunciation_rule_repository(self) -> CompanyPronunciationRuleRepository:
        """Per-company правила произношения TTS, shared БД."""
        return CompanyPronunciationRuleRepository(db_url=self.required_shared_db_url)

    @lazy
    def llm_model_score_repository(self) -> LLMModelScoreRepository:
        """Платформенный скоринг LLM-моделей, shared БД."""
        return LLMModelScoreRepository(db_url=self.required_shared_db_url)

    @lazy
    def ai_model_catalog_repository(self) -> AIModelCatalogRepository:
        """Shared provider model catalog for LLM, embedding, rerank and image capabilities."""
        return AIModelCatalogRepository(storage=self.shared_storage)

    @lazy
    def file_repository(self) -> FileRepository:
        """FileRepository для работы с файлами"""
        return FileRepository(storage=self.shared_storage)

    @lazy
    def files_service(self) -> FilesService:
        """FilesService — единственный путь create/register/get/bind/delete для FileRecord."""

        async def docs_bind_hook(placement: DocsPlacement) -> DocsBindResult:
            return await DocumentsClient().bind_file(placement)

        async def rag_index_hook(
            file_id: str,
            namespace_id: str,
            metadata: RAGMetadata | None,
        ) -> None:
            rag_metadata: RAGMetadata = metadata if metadata is not None else {}
            _ = await RagClient().index_file(
                namespace_id,
                file_id,
                metadata=rag_metadata,
            )

        return FilesService(
            file_repository=self.file_repository,
            docs_bind_hook=docs_bind_hook,
            rag_index_hook=rag_index_hook,
        )

    @lazy
    def file_purge_service(self) -> FilePurgeService:
        return FilePurgeService(file_repository=self.file_repository)

    @lazy
    def namespace_repository(self) -> NamespaceRepository:
        """NamespaceRepository для работы с namespace"""
        return NamespaceRepository(storage=self.shared_storage)

    @lazy
    def llm_context_memory_store(self) -> RAGLLMContextMemoryStore:
        """Хранилище эпизодической памяти в scope компании для generic LLM context layer."""
        return RAGLLMContextMemoryStore(
            repository=self.rag_repository,
            namespace_repository=self.namespace_repository,
        )

    # === Сервисы ===

    @lazy
    def text_transform_service(self) -> TextTransformService:
        """Generic текстовые трансформации на LLM для сервисов платформы."""
        return TextTransformService()

    @lazy
    def billing_service(self) -> BillingService:
        """BillingService для биллинга и учета использования"""
        settings = get_settings()
        tariff_prices_by_plan: dict[TariffPlan, dict[str, dict[str, float]]] = {
            TariffPlan(plan_value): tree
            for plan_value, tree in settings.billing.tariff_prices.items()
        }
        return BillingService(
            company_repository=self.company_repository,
            user_repository=self.user_repository,
            usage_repository=self.usage_repository,
            tariff_prices=tariff_prices_by_plan,
            resource_base_prices=settings.billing.resource_base_prices,
            shared_storage=self.shared_storage,
            balance_enforcement_enabled=settings.billing.balance_enforcement_enabled,
            balance_enforcement_exempt_company_ids=list(
                settings.billing.balance_enforcement_exempt_company_ids
            ),
        )

    @lazy
    def auth_service(self) -> AuthService:
        """AuthService для авторизации"""
        return AuthService(
            user_repository=self.user_repository,
            company_repository=self.company_repository,
            auth_session_repository=self.auth_session_repository,
            storage=self.shared_storage,
        )

    @lazy
    def integration_external_author_service(self) -> IntegrationExternalAuthorService:
        """Сопоставление внешних авторов интеграций с user_id (pre-provision, shared storage)."""
        return IntegrationExternalAuthorService(
            storage=self.shared_storage,
            user_repository=self.user_repository,
            company_repository=self.company_repository,
        )

    @lazy
    def variables_service(self) -> VariablesService:
        """VariablesService — единый фасад переменных компании поверх secrets-сервиса."""
        return VariablesService(secrets_client=self.secrets_client)

    @lazy
    def s3_factory(self):
        """S3ClientFactory для работы с S3"""
        return S3ClientFactory

    @lazy
    def service_client(self) -> ServiceClient:
        """ServiceClient для межсервисного взаимодействия"""
        return ServiceClient()

    @property
    def rag_provider(self):
        """Дефолтный RAG-провайдер: на каждый доступ — фабрика с учётом per-company override.

        НЕ ``@lazy``: per-company embedding override живёт в Context.active_company.metadata,
        и закешированный провайдер на жизнь процесса игнорировал бы переключение
        компании на её собственный embedding endpoint.
        """
        return get_rag_provider()

    @property
    def rag_repository(self) -> RAGRepository:
        """RAGRepository: in-process всегда ``pgvector``; per-request с учётом company override."""
        return RAGRepository(
            get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID),
            service_client=self.service_client,
        )

    @lazy
    def scheduler_client(self) -> SchedulerClient:
        """SchedulerClient для единого cron/control-plane."""
        return SchedulerClient(service_client=self.service_client)

    @lazy
    def integration_credential_repository(self) -> IntegrationCredentialRepository:
        """IntegrationCredentialRepository для per-user OAuth токенов"""
        return IntegrationCredentialRepository(db_url=self.required_shared_db_url)

    @lazy
    def oauth_service(self) -> OAuthService:
        """OAuthService — универсальный OAuth2 flow для внешних интеграций"""
        return OAuthService(
            repository=self.integration_credential_repository,
            storage=self.shared_storage,
        )

    @lazy
    def calendar_event_repository(self) -> CalendarEventSqlRepository:
        """Репозиторий событий календаря."""
        return CalendarEventSqlRepository(db_url=self.required_shared_db_url)

    @lazy
    def calendar_service(self) -> CalendarService:
        """CalendarService для платформенного календаря"""
        return CalendarService(
            event_repository=self.calendar_event_repository,
            oauth_service=self.oauth_service,
            credential_repository=self.integration_credential_repository,
            user_repository=self.user_repository,
            company_repository=self.company_repository,
            service_client=self.service_client,
        )

    @lazy
    def short_link_repository(self) -> ShortLinkRepository:
        """Репозиторий коротких ссылок."""
        return ShortLinkRepository(db_url=self.required_shared_db_url)

    @lazy
    def short_link_service(self) -> ShortLinkService:
        """Сервис коротких ссылок."""
        return ShortLinkService(repository=self.short_link_repository)

    @lazy
    def span_repository(self) -> SpanRepository:
        """SpanRepository для platform_tracing (отдельная БД)."""
        return SpanRepository(storage=self.tracing_storage)

    @lazy
    def push_subscription_repository(self) -> PushSubscriptionRepository:
        """PushSubscriptionRepository для push уведомлений"""
        return PushSubscriptionRepository(db_url=self.required_shared_db_url)

    # === CRUD роутеры ===

    def _register_crud_router(
        self,
        repository_name: str,
        repository: BaseRepository[_RepositoryModelT],
        prefix: str,
        tags: list[str],
        repository_dependency: Callable[[], BaseRepository[_RepositoryModelT]],
    ) -> None:
        """
        Регистрирует CRUD роутер для репозитория.

        Аргументы:
            repository_name: Имя репозитория (например, "flow_repository")
            repository: Экземпляр репозитория
            prefix: Префикс пути (например, "/flows")
            tags: Теги для OpenAPI
            repository_dependency: Dependency функция для получения репозитория
        """
        generator = CRUDRouterGenerator(
            repository=repository,
            prefix=prefix,
            tags=tags,
            repository_dependency=repository_dependency,
        )

        router = generator.generate_router()
        self._crud_routers[repository_name] = router

        logger.debug(f"CRUD роутер зарегистрирован: {repository_name} -> {prefix}")

    def get_crud_routers(self) -> list[APIRouter]:
        """
        Возвращает список всех зарегистрированных CRUD роутеров.

        Возвращает:
            Список APIRouter
        """
        return list(self._crud_routers.values())

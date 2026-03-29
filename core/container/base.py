"""
Базовый Dependency Injection Container с ленивой инициализацией.

Использование декоратора @lazy для сервисов:
    class MyContainer(BaseContainer):
        @lazy
        def my_service(self):
            from my_module import MyService
            return MyService(repository=self.my_repository)

Декоратор @lazy автоматически:
- Кэширует результат
- Превращает метод в property
- Добавляет логирование

ВАЖНО: BaseContainer НЕ зависит от app/* модулей!
"""

import functools
import logging
from typing import Optional, Any, Callable, Dict, List, Type, Union, get_args, TYPE_CHECKING
from fastapi import APIRouter

from core.db.http_repository import HTTPRepositoryProxy

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.db.base_repository import BaseRepository


def lazy(func: Callable) -> property:
    """
    Декоратор для ленивой инициализации сервисов с кэшированием.
    
    Превращает метод в property с автоматическим кэшированием результата.
    
    Пример:
        class Container(BaseContainer):
            @lazy
            def my_service(self):
                from my_module import MyService
                return MyService(repo=self.repository)
    """
    attr_name = f'_cached_{func.__name__}'
    
    @property
    @functools.wraps(func)
    def wrapper(self):
        cached = getattr(self, attr_name, None)
        if cached is None:
            cached = func(self)
            setattr(self, attr_name, cached)
            logger.debug(f"{func.__name__} инициализирован")
        return cached
    
    return wrapper


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
        db_url: Optional[str] = None, 
        shared_db_url: Optional[str] = None,
        service_db_url: Optional[str] = None  # Алиас для db_url
    ):
        """
        Args:
            db_url: URL service БД (или service_db_url)
            shared_db_url: URL shared БД для User, Company, Session
            service_db_url: Алиас для db_url (для совместимости)
        """
        self.db_url = service_db_url or db_url
        if shared_db_url is None:
            from core.config import get_settings
            settings = get_settings()
            shared_db_url = settings.database.shared_url
        self.shared_db_url = shared_db_url
        
        self._crud_routers: Dict[str, APIRouter] = {}
        self._service_name: Optional[str] = None
    
    @property
    def service_name(self) -> str:
        """
        Имя текущего сервиса из settings.server.name.
        Используется для определения локальный репозиторий или HTTP прокси.
        """
        if self._service_name is None:
            from core.config import get_settings
            self._service_name = get_settings().server.name
        return self._service_name
    
    def _get_repository(
        self,
        repository_class: Type["BaseRepository"],
        storage: Optional[Any] = None
    ) -> Union["BaseRepository", Any]:
        """
        Возвращает локальный репозиторий или HTTP прокси.
        
        Если owner_service репозитория совпадает с текущим сервисом,
        создается локальный репозиторий с доступом к БД.
        Иначе создается HTTPRepositoryProxy для HTTP запросов.
        
        Args:
            repository_class: Класс репозитория
            storage: Storage для локального репозитория (опционально)
            
        Returns:
            Локальный репозиторий или HTTPRepositoryProxy
        """
        if repository_class.owner_service == self.service_name:
            if storage is None:
                storage = self.shared_storage if repository_class.is_global else self.storage
            return repository_class(storage=storage)
        
        # Извлекаем model_class из generic параметра BaseRepository[T]
        model_class = None
        for base in getattr(repository_class, '__orig_bases__', []):
            args = get_args(base)
            if args:
                model_class = args[0]
                break
        
        return HTTPRepositoryProxy(
            repository_class=repository_class,
            model_class=model_class
        )
    
    # === Storage ===
    
    @lazy
    def storage(self):
        """Service Storage для работы с БД"""
        from core.db.storage import Storage
        from core.context import get_context
        return Storage(db_url=self.db_url, get_context_func=get_context)
    
    @lazy
    def shared_storage(self):
        """Shared Storage для работы с общими данными (users, companies)"""
        from core.db.storage import Storage
        from core.context import get_context
        return Storage(db_url=self.shared_db_url, get_context_func=get_context)
    
    # === Репозитории (shared БД) ===
    
    @lazy
    def user_repository(self):
        """UserRepository для работы с пользователями"""
        from core.db.repositories.user_repository import UserRepository
        return UserRepository(storage=self.shared_storage)
    
    @lazy
    def company_repository(self):
        """CompanyRepository для работы с компаниями"""
        from core.db.repositories.company_repository import CompanyRepository
        return CompanyRepository(storage=self.shared_storage)
    
    @lazy
    def auth_session_repository(self):
        """AuthSessionRepository для работы с сессиями авторизации"""
        from core.db.repositories.auth_session_repository import AuthSessionRepository
        return AuthSessionRepository(storage=self.shared_storage)
    
    @lazy
    def subdomain_repository(self):
        """SubdomainRepository для работы с поддоменами"""
        from core.db.repositories.subdomain_repository import SubdomainRepository
        return SubdomainRepository(storage=self.shared_storage)
    
    @lazy
    def variable_repository(self):
        """VariableRepository для работы с переменными"""
        from core.db.repositories.variable_repository import VariableRepository
        return VariableRepository(storage=self.shared_storage)
    
    @lazy
    def usage_repository(self):
        """UsageRepository для работы с использованием"""
        from core.db.repositories.usage_repository import UsageRepository
        return UsageRepository(storage=self.shared_storage)
    
    @lazy
    def file_repository(self):
        """FileRepository для работы с файлами"""
        from core.files.file_repository import FileRepository
        return FileRepository(storage=self.shared_storage)
    
    @lazy
    def namespace_repository(self):
        """NamespaceRepository для работы с namespace"""
        from core.db.repositories.namespace_repository import NamespaceRepository
        return NamespaceRepository(storage=self.shared_storage)
    
    # === Сервисы ===
    
    @lazy
    def billing_service(self):
        """BillingService для биллинга и учета использования"""
        from core.billing import BillingService
        return BillingService(
            company_repository=self.company_repository,
            user_repository=self.user_repository,
            usage_repository=self.usage_repository
        )
    
    @lazy
    def auth_service(self):
        """AuthService для авторизации"""
        from core.identity.auth_service import AuthService
        return AuthService(
            user_repository=self.user_repository,
            company_repository=self.company_repository,
            auth_session_repository=self.auth_session_repository
        )
    
    @lazy
    def variables_service(self):
        """VariablesService для работы с переменными"""
        from core.variables.service import VariablesService
        return VariablesService(variable_repository=self.variable_repository)
    
    @lazy
    def s3_factory(self):
        """S3ClientFactory для работы с S3"""
        from core.files.s3_client import S3ClientFactory
        return S3ClientFactory
    
    @lazy
    def service_client(self):
        """ServiceClient для межсервисного взаимодействия"""
        from core.clients.service_client import ServiceClient
        return ServiceClient()

    @lazy
    def scheduler_client(self):
        """SchedulerClient для единого cron/control-plane."""
        from core.clients.scheduler_client import SchedulerClient
        return SchedulerClient(service_client=self.service_client)

    @lazy
    def calendar_service(self):
        """CalendarService для платформенного календаря"""
        from core.calendar.repositories import CalendarEventSqlRepository, CalendarIntegrationSqlRepository
        from core.calendar.service import CalendarService
        return CalendarService(
            event_repository=CalendarEventSqlRepository(db_url=self.shared_db_url),
            integration_repository=CalendarIntegrationSqlRepository(db_url=self.shared_db_url),
            service_client=self.service_client,
            storage=self.shared_storage,
        )
    
    @lazy
    def span_repository(self):
        """SpanRepository для сохранения трейсов в shared БД"""
        from core.tracing.repository import SpanRepository
        return SpanRepository(storage=self.shared_storage)
    
    @lazy
    def push_subscription_repository(self):
        """PushSubscriptionRepository для push уведомлений"""
        from core.push.repository import PushSubscriptionRepository
        return PushSubscriptionRepository(db_url=self.shared_db_url)
    
    # === CRUD роутеры ===
    
    def _register_crud_router(
        self,
        repository_name: str,
        repository: Any,
        prefix: str,
        tags: List[str],
        repository_dependency: Callable
    ):
        """
        Регистрирует CRUD роутер для репозитория.
        
        Args:
            repository_name: Имя репозитория (например, "flow_repository")
            repository: Экземпляр репозитория
            prefix: Префикс пути (например, "/flows")
            tags: Теги для OpenAPI
            repository_dependency: Dependency функция для получения репозитория
        """
        from core.api.crud_router import CRUDRouterGenerator
        
        generator = CRUDRouterGenerator(
            repository=repository,
            prefix=prefix,
            tags=tags,
            repository_dependency=repository_dependency
        )
        
        router = generator.generate_router()
        self._crud_routers[repository_name] = router
        
        logger.debug(f"CRUD роутер зарегистрирован: {repository_name} -> {prefix}")
    
    def get_crud_routers(self) -> List[APIRouter]:
        """
        Возвращает список всех зарегистрированных CRUD роутеров.
        
        Returns:
            Список APIRouter
        """
        return list(self._crud_routers.values())

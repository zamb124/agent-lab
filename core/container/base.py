"""
Базовый Dependency Injection Container.

Архитектура:
- BaseContainer содержит только базовые сервисы (storage, auth_service, variables_service)
- Сервисы (apps/agents, apps/frontend) наследуют BaseContainer и добавляют свои сервисы
- Ленивая инициализация через __getattr__
- Каждый сервис имеет свой изолированный контейнер

ВАЖНО: BaseContainer НЕ зависит от app/* модулей!
ВАЖНО: Сервисы используют свои контейнеры (get_agents_container, get_frontend_container),
       а не глобальный системный контейнер. Контейнер доступен через request.app.state.container.
"""

import asyncio
import logging
from typing import Optional, TYPE_CHECKING

from core.db.storage import Storage
from core.db.database import get_session_factory
from core.context import get_context
from core.identity.auth_service import AuthService
from core.files.s3_client import S3ClientFactory

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
    from core.db.repositories.user_repository import UserRepository
    from core.db.repositories.company_repository import CompanyRepository
    from core.db.repositories.auth_session_repository import AuthSessionRepository
    from core.db.repositories.subdomain_repository import SubdomainRepository
    from core.db.repositories.variable_repository import VariableRepository
    from core.db.repositories.usage_repository import UsageRepository
    from core.files.file_repository import FileRepository

logger = logging.getLogger(__name__)


class BaseContainer:
    """
    Базовый контейнер зависимостей с ленивой инициализацией.
    
    Содержит только базовые сервисы:
    - storage: Storage
    - engine: AsyncEngine
    - session_factory: async_sessionmaker
    
    Сервисы расширяют этот класс и добавляют свои зависимости.
    """

    def __init__(self, db_url: Optional[str] = None, shared_db_url: Optional[str] = None):
        """
        Args:
            db_url: URL БД (опционально, по умолчанию из settings)
            shared_db_url: URL shared БД для User, Company, Session (опционально, по умолчанию из settings.database.shared_url)
        """
        self.db_url = db_url
        if shared_db_url is None:
            from core.config import get_settings
            settings = get_settings()
            shared_db_url = settings.database.shared_url
        self.shared_db_url = shared_db_url
        self.engine: Optional["AsyncEngine"] = None
        self._session_factory: Optional["async_sessionmaker"] = None
        self._storage: Optional["Storage"] = None
        self._shared_storage: Optional["Storage"] = None
        self._user_repository: Optional["UserRepository"] = None
        self._company_repository: Optional["CompanyRepository"] = None
        self._auth_session_repository: Optional["AuthSessionRepository"] = None
        self._subdomain_repository: Optional["SubdomainRepository"] = None
        self._variable_repository: Optional["VariableRepository"] = None
        self._usage_repository: Optional["UsageRepository"] = None
        self._file_repository: Optional["FileRepository"] = None
        self._auth_service: Optional["AuthService"] = None
        self._s3_factory: Optional["S3ClientFactory"] = None
        self._initialized = False

    def _ensure_initialized(self):
        """Инициализирует базовые зависимости если еще не инициализированы"""
        if not self._initialized:
            self._initialized = True

    def __getattr__(self, name: str):
        """Ленивая инициализация сервисов при обращении к атрибутам"""
        
        if name == 'storage':
            if self._storage is None:
                self._storage = Storage(db_url=self.db_url, get_context_func=get_context)
                logger.debug("Storage инициализирован в BaseContainer")
            return self._storage
        
        if name == 'shared_storage':
            if self._shared_storage is None:
                self._shared_storage = Storage(db_url=self.shared_db_url, get_context_func=get_context)
                logger.debug("Shared Storage инициализирован в BaseContainer")
            return self._shared_storage
        
        if name == 'session_factory':
            if self._session_factory is None:
                loop = asyncio.get_running_loop()
                self._session_factory = loop.run_until_complete(get_session_factory(self.db_url))
                logger.debug("Session factory инициализирован в BaseContainer")
            return self._session_factory
        
        if name == 'user_repository':
            if self._user_repository is None:
                from core.db.repositories.user_repository import UserRepository
                self._user_repository = UserRepository(storage=self.shared_storage)
                logger.debug("UserRepository инициализирован в BaseContainer")
            return self._user_repository
        
        if name == 'company_repository':
            if self._company_repository is None:
                from core.db.repositories.company_repository import CompanyRepository
                self._company_repository = CompanyRepository(storage=self.shared_storage)
                logger.debug("CompanyRepository инициализирован в BaseContainer")
            return self._company_repository
        
        if name == 'auth_session_repository':
            if self._auth_session_repository is None:
                from core.db.repositories.auth_session_repository import AuthSessionRepository
                self._auth_session_repository = AuthSessionRepository(storage=self.shared_storage)
                logger.debug("AuthSessionRepository инициализирован в BaseContainer")
            return self._auth_session_repository
        
        if name == 'subdomain_repository':
            if self._subdomain_repository is None:
                from core.db.repositories.subdomain_repository import SubdomainRepository
                self._subdomain_repository = SubdomainRepository(storage=self.shared_storage)
                logger.debug("SubdomainRepository инициализирован в BaseContainer")
            return self._subdomain_repository
        
        if name == 'variable_repository':
            if self._variable_repository is None:
                from core.db.repositories.variable_repository import VariableRepository
                self._variable_repository = VariableRepository(storage=self.shared_storage)
                logger.debug("VariableRepository инициализирован в BaseContainer (shared БД)")
            return self._variable_repository
        
        if name == 'usage_repository':
            if self._usage_repository is None:
                from core.db.repositories.usage_repository import UsageRepository
                self._usage_repository = UsageRepository(storage=self.shared_storage)
                logger.debug("UsageRepository инициализирован в BaseContainer (shared БД)")
            return self._usage_repository
        
        if name == 'file_repository':
            if self._file_repository is None:
                from core.files.file_repository import FileRepository
                self._file_repository = FileRepository(storage=self.shared_storage)
                logger.debug("FileRepository инициализирован в BaseContainer (shared БД)")
            return self._file_repository
        
        if name == 'variables_service':
            if not hasattr(self, '_variables_service') or self._variables_service is None:
                from core.variables.service import VariablesService
                self._variables_service = VariablesService(variable_repository=self.variable_repository)
                logger.debug("VariablesService инициализирован в BaseContainer")
            return self._variables_service
        
        if name == 'auth_service':
            if self._auth_service is None:
                self._auth_service = AuthService(
                    user_repository=self.user_repository,
                    company_repository=self.company_repository,
                    auth_session_repository=self.auth_session_repository
                )
                logger.debug("AuthService инициализирован в BaseContainer")
            return self._auth_service
        
        if name == 's3_factory':
            if self._s3_factory is None:
                self._s3_factory = S3ClientFactory
                logger.debug("S3ClientFactory инициализирован в BaseContainer")
            return self._s3_factory
        
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

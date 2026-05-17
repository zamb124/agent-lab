"""
Dependency Injection контейнер для Frontend
"""

from typing import Optional

from apps.flows.src.db.flow_repository import FlowRepository
from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.container import BaseContainer, lazy
from core.context import get_context
from core.db.repositories.api_key_repository import ApiKeyRepository
from core.db.repositories.auth_session_repository import AuthSessionRepository
from core.db.repositories.company_repository import CompanyRepository
from core.db.repositories.embed_config_repository import EmbedConfigRepository
from core.db.repositories.embed_mapping_repository import EmbedMappingRepository
from core.db.repositories.usage_repository import UsageRepository
from core.db.repositories.user_repository import UserRepository
from core.db.storage import Storage
from core.identity.auth_service import AuthService
from core.logging import get_logger
from core.payments import PaymentService

logger = get_logger(__name__)
class FrontendContainer(BaseContainer):
    """Контейнер зависимостей для Frontend"""

    @lazy
    def user_repository(self):
        """Репозиторий пользователей (для тестов и прямого доступа)"""
        return UserRepository(storage=self.shared_storage)

    @lazy
    def company_repository(self):
        """Репозиторий компаний (для тестов и прямого доступа)"""
        return CompanyRepository(storage=self.shared_storage)

    @lazy
    def auth_service(self) -> AuthService:
        """AuthService для OAuth авторизации"""
        return AuthService(
            user_repository=self.user_repository,
            company_repository=self.company_repository,
            auth_session_repository=AuthSessionRepository(storage=self.shared_storage)
        )

    @lazy
    def embed_config_repository(self):
        """Репозиторий для конфигураций встраиваемых виджетов"""
        return EmbedConfigRepository(storage=self.shared_storage)

    @lazy
    def embed_mapping_repository(self):
        """Репозиторий для глобального маппинга embed_id -> company_id"""
        return EmbedMappingRepository(storage=self.shared_storage)

    @lazy
    def usage_repository(self):
        """Репозиторий для записей использования ресурсов"""
        return UsageRepository(storage=self.shared_storage)

    @lazy
    def api_key_repository(self):
        return ApiKeyRepository(db_url=self.required_shared_db_url)

    @lazy
    def payment_service(self):
        return PaymentService(company_repository=self.company_repository)

    @lazy
    def flows_flow_repository(self):
        """Репозиторий flows из сервисной БД flows (read-only сценарии без HTTP к peers)."""
        url = get_settings().database.flows_url
        if not url:
            return None
        storage = Storage(db_url=url, get_context_func=get_context)
        return FlowRepository(storage=storage)

    @lazy
    def redis_client(self):
        return RedisClient(get_settings().database.redis_url)

# === Глобальный контейнер ===

_frontend_container: Optional[FrontendContainer] = None

def get_frontend_container() -> FrontendContainer:
    """Получает контейнер (создает при первом вызове)"""
    global _frontend_container
    if _frontend_container is None:
        settings = get_settings()

        if not settings.database.shared_url:
            raise ValueError("database.shared_url не задан")

        _frontend_container = FrontendContainer(
            db_url=settings.database.shared_url,
            shared_db_url=settings.database.shared_url
        )
        logger.info("FrontendContainer инициализирован")
    return _frontend_container

def set_frontend_container(container: FrontendContainer):
    """Устанавливает контейнер (для тестов)"""
    global _frontend_container
    _frontend_container = container

def reset_frontend_container():
    """Сбрасывает контейнер (для тестов)"""
    global _frontend_container
    _frontend_container = None

# Алиас для совместимости
get_container = get_frontend_container

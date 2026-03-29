"""
Core - общая инфраструктура Humanitec.

Независимый модуль, который НЕ зависит от apps/.
Содержит базовые компоненты для всех сервисов платформы.

Структура:
- config/       - Конфигурация (каскадная загрузка)
- db/           - База данных (Storage, BaseRepository)
- models/       - Базовые модели (User, Company, Context)
- context/      - Глобальный контекст (contextvars)
- http/         - HTTP клиенты с прокси
- logging/      - Логирование (JSON, Structured)
- container/    - DI контейнер (BaseContainer)
- variables/    - Переменные компаний (резолюция @var:key)
- files/        - Файлы и S3 (S3Client, FileProcessor)
- clients/      - Клиенты (LLM, NanoBanana, STT, Payment)
- utils/        - Утилиты (tokens, slug)
- middleware/   - Middleware
- identity/     - Идентификация
- i18n/         - Интернационализация
"""

__version__ = "1.0.0"

from core.config import get_settings, load_merged_config, BaseSettings
from core.db import Storage, BaseRepository, BaseSQLRepository, get_engine
from core.models import User, Company, Context, Language, AuthProvider, ProviderUserInfo, AuthResult
from core.context import get_context, set_context, clear_context
from core.auth import (
    permission_checker,
    PermissionChecker,
    PermissionDeniedError,
    ADMIN_GROUP,
    DEFAULT_PERMISSION,
)
from core.http import get_httpx_client
from core.logging import setup_logging, get_logger
from core.container import BaseContainer
from core.variables import VariablesService, VariableResolver, get_state, set_state_in_context
# RAG imports moved to core.rag
from core.billing import BillingService
from core.payments import PaymentService, PaymentSyncService
from core.files import S3Client, FileProcessor, AudioProcessor, FileMetadata
from core.clients import get_llm, NanoBananaClient, PaymentProviderFactory
from core.identity import AuthService
from core.i18n import get_translation_manager, t
from core.utils import get_token_service, generate_slug
from core.fields import Field

__all__ = [
    "get_settings",
    "load_merged_config",
    "BaseSettings",
    "Storage",
    "BaseRepository",
    "BaseSQLRepository",
    "get_engine",
    "permission_checker",
    "PermissionChecker",
    "PermissionDeniedError",
    "ADMIN_GROUP",
    "DEFAULT_PERMISSION",
    "User",
    "Company",
    "Context",
    "Language",
    "AuthProvider",
    "ProviderUserInfo",
    "AuthResult",
    "AuthService",
    "get_context",
    "set_context",
    "clear_context",
    "get_httpx_client",
    "setup_logging",
    "get_logger",
    "BaseContainer",
    "VariablesService",
    "VariableResolver",
    "get_state",
    "set_state_in_context",
    "S3Client",
    "FileProcessor",
    "AudioProcessor",
    "FileMetadata",
    "get_llm",
    "NanoBananaClient",
    "PaymentProviderFactory",
    "get_translation_manager",
    "t",
    "get_token_service",
    "generate_slug",
    "Field",
    "BillingService",
    "PaymentService",
    "PaymentSyncService",
]

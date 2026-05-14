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

from core.auth import (
    ADMIN_GROUP,
    DEFAULT_PERMISSION,
    PermissionChecker,
    PermissionDeniedError,
    permission_checker,
)

# RAG imports moved to core.rag
from core.billing import BillingService
from core.clients import NanoBananaClient, PaymentProviderFactory, get_llm
from core.config import BaseSettings, get_settings, load_merged_config
from core.container import BaseContainer
from core.context import clear_context, get_context, set_context
from core.db import BaseRepository, BaseSQLRepository, Storage, get_engine
from core.fields import Field
from core.files import AudioProcessor, FileMetadata, FileProcessor, S3Client
from core.http import get_httpx_client
from core.i18n import get_translation_manager, t
from core.identity import AuthService
from core.logging import get_logger, setup_logging
from core.models import AuthProvider, AuthResult, Company, Context, Language, ProviderUserInfo, User
from core.payments import PaymentService, PaymentSyncService
from core.utils import generate_slug, get_token_service
from core.variables import VariableResolver, VariablesService, get_state, set_state_in_context

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

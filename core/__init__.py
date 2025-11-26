"""
Core - общая инфраструктура Agent Lab.

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
- clients/      - Клиенты (LLM, NanoBanana, CloudVoice, Payment)
- utils/        - Утилиты (tokens, slug)
- middleware/   - Middleware
- identity/     - Идентификация
- i18n/         - Интернационализация
"""

__version__ = "1.0.0"

from core.config import get_settings, load_merged_config, BaseSettings
from core.db import Storage, BaseRepository, get_engine, create_tables
from core.models import User, Company, Context, Language, AuthProvider, ProviderUserInfo, AuthResult
from core.context import get_context, set_context, clear_context
from core.http import get_httpx_client
from core.logging import setup_logging, get_logger
from core.container import BaseContainer, get_system_container, set_system_container, initialize_system_container
from core.variables import VariablesService, VariableResolver, get_state, set_state_in_context
from core.rag import (
    BaseRAGProvider,
    RAGDocument,
    RAGSearchResult,
    RAGNamespace,
    AgentRAGConfig,
    get_rag_provider,
    get_default_rag_provider,
    close_default_rag_provider
)
from core.billing import BillingService
from core.payments import PaymentService, PaymentSyncService
from core.files import S3Client, FileProcessor, AudioProcessor, FileMetadata
from core.clients import get_llm, NanoBananaClient, CloudVoiceClient, PaymentProviderFactory
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
    "get_engine",
    "create_tables",
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
    "get_system_container",
    "set_system_container",
    "initialize_system_container",
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
    "CloudVoiceClient",
    "PaymentProviderFactory",
    "get_translation_manager",
    "t",
    "get_token_service",
    "generate_slug",
    "Field",
    "BaseRAGProvider",
    "RAGDocument",
    "RAGSearchResult",
    "RAGNamespace",
    "AgentRAGConfig",
    "get_rag_provider",
    "get_default_rag_provider",
    "close_default_rag_provider",
    "BillingService",
    "PaymentService",
    "PaymentSyncService",
]

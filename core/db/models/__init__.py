"""
Пакет SQLAlchemy-моделей платформы.

Реэкспортирует Base и все модели из под-модулей для обратной совместимости.
"""

from core.db.models.base import Base
from core.db.models.platform import (
    CalendarEventRecord,
    CalendarIntegrationRecord,
    IntegrationCredentialRecord,
    Namespaces,
    PlatformShortLink,
    PushSubscription,
    SchedulerTaskRecord,
    Storage,
    Usage,
    Users,
    Variables,
)
from core.db.models.rag import (
    DocumentProcessingStatus,
    VectorDocument,
)
from core.db.models.tracing import Spans

__all__ = [
    "Base",
    "Storage",
    "Users",
    "Variables",
    "Usage",
    "Namespaces",
    "Spans",
    "PushSubscription",
    "CalendarEventRecord",
    "CalendarIntegrationRecord",
    "IntegrationCredentialRecord",
    "SchedulerTaskRecord",
    "PlatformShortLink",
    "DocumentProcessingStatus",
    "VectorDocument",
]

"""
Пакет SQLAlchemy-моделей платформы.

Реэкспортирует Base и все модели из под-модулей для обратной совместимости.
"""

from core.db.models.base import Base
from core.db.models.platform import (
    Storage,
    Users,
    Variables,
    Usage,
    Namespaces,
    PushSubscription,
    CalendarEventRecord,
    CalendarIntegrationRecord,
    SchedulerTaskRecord,
)
from core.db.models.tracing import Spans
from core.db.models.rag import (
    DocumentProcessingStatus,
    VectorDocument,
)

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
    "SchedulerTaskRecord",
    "DocumentProcessingStatus",
    "VectorDocument",
]

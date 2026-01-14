"""
Модели для Web Push подписок
"""
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB

from core.db.models import Base
from core.db.service_registry import register_service
from core.config import get_settings


def _get_shared_db_url() -> str:
    """Получает URL shared БД из конфига."""
    settings = get_settings()
    return settings.database.shared_url or settings.database.url


# Регистрируем push сервис для миграций (использует shared БД)
register_service("push", _get_shared_db_url, "core.push.models")


class PushSubscription(Base):
    """Подписка пользователя на push-уведомления"""
    __tablename__ = "push_subscriptions"

    id = Column(String(255), primary_key=True, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    endpoint = Column(String(2048), nullable=False, unique=True)
    keys = Column(JSONB, nullable=False)  # {"p256dh": "...", "auth": "..."}
    user_agent = Column(String(512), nullable=True)
    platform = Column(String(50), nullable=True)  # ios, android, desktop
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_used_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index('ix_push_subscriptions_user_endpoint', 'user_id', 'endpoint'),
    )

    def __repr__(self):
        return f"<PushSubscription(user_id={self.user_id}, platform={self.platform})>"

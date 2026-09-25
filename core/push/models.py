"""Подписка на push. Таблица ``push_subscriptions`` в ``platform_shared``."""

import uuid
from datetime import datetime, timezone
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from core.logging import get_logger
from core.models.platform_model import PlatformModel
from core.types import PushSubscriptionKeys

logger = get_logger(__name__)


class PushSubscription(PlatformModel):
    """Подписка пользователя. Адрес доставки — уникальный ``endpoint``."""

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    push_subscription_id: str = DbField(db_pk=True)

    class Meta:
        is_table: bool = True
        table_name: str = "push_subscriptions"
        indexes: list[Index] = [Index(("user_id", "endpoint"))]

    user_id: str = DbField(db_index=True)
    endpoint: str = DbField(db_unique=True, max_length=2048)
    keys: PushSubscriptionKeys = DbField(db_type="JSONB")
    user_agent: str | None = DbField(default=None, max_length=512)
    platform: str | None = DbField(default=None, max_length=50)
    created_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc), db_index=True)

    @classmethod
    async def list_for_user(cls, user_id: str) -> list[Self]:
        return await cls.objects.filter(user_id=user_id).order_by("-last_used_at").all()

    @classmethod
    async def upsert_by_endpoint(
        cls,
        user_id: str,
        endpoint: str,
        keys: PushSubscriptionKeys,
        platform: str = "unknown",
        user_agent: str | None = None,
    ) -> Self:
        now = datetime.now(timezone.utc)
        existing = await cls.objects.filter(endpoint=endpoint).get_or_none()
        if existing is None:
            created = cls(
                push_subscription_id=str(uuid.uuid4()),
                user_id=user_id,
                endpoint=endpoint,
                keys=keys,
                platform=platform,
                user_agent=user_agent,
                created_at=now,
                last_used_at=now,
            )
            _ = await cls.objects.create(instance=created)
            logger.info("push.subscription.upserted", user_id=user_id, platform=platform)
            return created
        existing.user_id = user_id
        existing.keys = keys
        existing.platform = platform
        existing.user_agent = user_agent
        existing.last_used_at = now
        _ = await existing.save()
        logger.info("push.subscription.upserted", user_id=user_id, platform=platform)
        return existing

    @classmethod
    async def delete_by_user_and_endpoint(cls, user_id: str, endpoint: str) -> bool:
        deleted = await cls.objects.filter(user_id=user_id, endpoint=endpoint).delete()
        if deleted > 0:
            logger.info("push.subscription.deleted", user_id=user_id)
        return deleted > 0

    @classmethod
    async def delete_by_endpoint(cls, endpoint: str) -> bool:
        deleted = await cls.objects.filter(endpoint=endpoint).delete()
        if deleted > 0:
            logger.info("push.endpoint.expired")
        return deleted > 0

"""
Репозиторий для работы с push-подписками.

Использует паттерн как DocumentStatusRepository:
- Принимает db_url
- Создает session factory
- Работает с нормализованной таблицей push_subscriptions
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.db.database import get_session_factory
from core.db.models import PushSubscription
from core.db.utils import get_rowcount
from core.logging import get_logger
from core.types import PushSubscriptionKeys

logger = get_logger(__name__)


class PushSubscriptionRepository:
    """
    Репозиторий для push-подписок.

    Паттерн аналогичен DocumentStatusRepository:
    - Принимает db_url в конструкторе
    - Использует get_session_factory для работы с БД
    """

    def __init__(self, db_url: str) -> None:
        """
        Args:
            db_url: URL базы данных (shared БД)
        """
        self._db_url: str = db_url
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def _get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Получает session factory (с кешированием)"""
        if self._session_factory is None:
            self._session_factory = await get_session_factory(self._db_url)
        return self._session_factory

    async def get_user_subscriptions(self, user_id: str) -> list[PushSubscription]:
        """
        Получить все подписки пользователя.

        Args:
            user_id: ID пользователя

        Returns:
            Список подписок
        """
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(PushSubscription)
                .where(PushSubscription.user_id == user_id)
                .order_by(PushSubscription.last_used_at.desc())
            )
            return list(result.scalars().all())

    async def upsert_subscription(
        self,
        user_id: str,
        endpoint: str,
        keys: PushSubscriptionKeys,
        platform: str = "unknown",
        user_agent: str | None = None,
    ) -> PushSubscription:
        """
        Создать или обновить подписку.

        Если подписка с таким endpoint существует - обновляет.
        Иначе создает новую.

        Args:
            user_id: ID пользователя
            endpoint: Push endpoint URL
            keys: VAPID keys (p256dh, auth)
            platform: Платформа (desktop, ios, android)
            user_agent: User-Agent браузера

        Returns:
            Созданная или обновленная подписка
        """
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            now = datetime.now(timezone.utc)

            stmt = (
                insert(PushSubscription)
                .values(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    endpoint=endpoint,
                    keys=keys,
                    platform=platform,
                    user_agent=user_agent,
                    created_at=now,
                    last_used_at=now,
                )
                .on_conflict_do_update(
                    index_elements=["endpoint"],
                    set_={
                        "user_id": user_id,
                        "keys": keys,
                        "platform": platform,
                        "user_agent": user_agent,
                        "last_used_at": now,
                    },
                )
                .returning(PushSubscription)
            )

            result = await session.execute(stmt)
            await session.commit()

            subscription = result.scalar_one()
            logger.info(f"Push подписка upsert: user={user_id}, platform={platform}")

            return subscription

    async def delete_subscription(self, user_id: str, endpoint: str) -> bool:
        """
        Удалить подписку.

        Args:
            user_id: ID пользователя
            endpoint: Push endpoint URL

        Returns:
            True если удалено, False если не найдено
        """
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                delete(PushSubscription)
                .where(PushSubscription.user_id == user_id)
                .where(PushSubscription.endpoint == endpoint)
            )
            await session.commit()

            deleted = get_rowcount(result) > 0
            if deleted:
                logger.info(f"Push подписка удалена: user={user_id}")

            return deleted

    async def delete_by_endpoint(self, endpoint: str) -> bool:
        """
        Удалить подписку по endpoint (для expired подписок).

        Args:
            endpoint: Push endpoint URL

        Returns:
            True если удалено
        """
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                delete(PushSubscription).where(PushSubscription.endpoint == endpoint)
            )
            await session.commit()

            deleted = get_rowcount(result) > 0
            if deleted:
                logger.info("Push подписка удалена по endpoint (expired)")

            return deleted

    async def touch_subscription(self, endpoint: str) -> None:
        """
        Обновить last_used_at для подписки.

        Args:
            endpoint: Push endpoint URL
        """
        session_factory = await self._get_session_factory()
        async with session_factory() as session:
            _ = await session.execute(
                update(PushSubscription)
                .where(PushSubscription.endpoint == endpoint)
                .values(last_used_at=datetime.now(timezone.utc))
            )
            await session.commit()

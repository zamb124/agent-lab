"""CustomerNotifyService — личные уведомления покупателю (кабинет).

Каналы — те же, что и у customer-auth: брендовые боты TG/MAX платформы
(`PhoneVerificationRegistry` на apex), `provider_user_id` identity — chat_id.
Дополнительно текст складывается в Redis-outbox
`customers:notify:{customer_id}` — e2e читают его без внешних сетей.

Деградация мягкая: у покупателя может не быть мессенджер-identity — тогда
уведомление живёт только в outbox/кабинете. Ошибка провайдера не роняет
задачу-источник: возвращается False.
"""

from __future__ import annotations

import json

from core.clients.phone_verification.registry import PhoneVerificationRegistry
from core.clients.redis_client import RedisClient
from core.config.models import CustomerAuthConfig
from core.customers.enums import CustomerIdentityProvider, PhoneVerificationMethod
from core.customers.models import CustomerIdentity
from core.logging import get_logger

logger = get_logger(__name__)

_OUTBOX_TTL_S = 7 * 86400


def notify_outbox_key(customer_id: str) -> str:
    """Ключ Redis-outbox уведомлений покупателя (тесты читают его напрямую)."""
    return f"customers:notify:{customer_id}"


class CustomerNotifyService:
    """Отправка текста покупателю: DM в TG/MAX бренда + Redis-outbox."""

    def __init__(
        self,
        *,
        cfg: CustomerAuthConfig,
        env: str,
        redis: RedisClient,
    ) -> None:
        self._cfg: CustomerAuthConfig = cfg
        self._env: str = env
        self._redis: RedisClient = redis

    async def _outbox_push(self, customer_id: str, text: str) -> None:
        _ = await self._redis.rpush(
            notify_outbox_key(customer_id),
            json.dumps({"text": text}, ensure_ascii=False),
            ttl_seconds=_OUTBOX_TTL_S,
        )

    async def send_text(self, customer_id: str, text: str, *, apex: str) -> bool:
        """Доставить текст по мессенджер-identity покупателя; False — каналов нет.

        `apex` выбирает бренд бота: покупатель подтверждал номер именно у
        брендового бота, DM приходит от него же.
        """
        delivered = False
        try:
            await self._outbox_push(customer_id, text)
        except Exception as exc:
            logger.warning(
                "customers.notify.outbox_failed",
                customer_id=customer_id,
                error=str(exc),
            )
        identities = await CustomerIdentity.list_for_customer(customer_id)
        if not identities:
            return False
        registry = PhoneVerificationRegistry.build(self._cfg, apex, env=self._env)
        telegram = registry.contact_share.get(PhoneVerificationMethod.TELEGRAM_CONTACT)
        max_bot = registry.contact_share.get(PhoneVerificationMethod.MAX_CONTACT)
        for identity in identities:
            try:
                if (
                    identity.provider == CustomerIdentityProvider.TELEGRAM
                    and telegram is not None
                    and telegram.available()
                ):
                    await telegram.send_text(identity.provider_user_id, text)
                    delivered = True
                elif (
                    identity.provider == CustomerIdentityProvider.MAX
                    and max_bot is not None
                    and max_bot.available()
                ):
                    await max_bot.send_text(identity.provider_user_id, text)
                    delivered = True
            except Exception as exc:
                logger.warning(
                    "customers.notify.send_failed",
                    customer_id=customer_id,
                    provider=identity.provider.value,
                    error=str(exc),
                )
        return delivered

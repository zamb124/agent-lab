#!/usr/bin/env python3
"""Регистрация customer-auth webhook'ов у бот-провайдеров.

``python -m scripts.customers.sync_bot_webhooks [--service-segment shop]``

Для каждого бренда ``customer_auth.brands``:
- Telegram: ``polling_enabled`` → ``deleteWebhook`` (getUpdates-режим);
  иначе ``setWebhook`` на ``/webhooks/telegram`` с ``webhook_secret``.
- MAX: ``POST /subscriptions`` с ``bot_started``+``message_created``.

Идемпотентно — запускать после деплоя, смены домена или ротации секретов.
Webhook-роут смонтирован на любом сервисе под ``/<segment>/api/v1/public/``;
по умолчанию используется витрина ``shop``.
"""

from __future__ import annotations

import argparse
import asyncio

from core.clients.phone_verification.max_bot import MaxContactProvider
from core.clients.phone_verification.telegram_bot import TelegramContactProvider
from core.config import get_settings
from core.config.models import CustomerAuthBrandConfig
from core.logging import get_logger

logger = get_logger(__name__)

_PUBLIC_PREFIX = "api/v1/public/customer-auth"


async def _sync_brand(apex: str, brand: CustomerAuthBrandConfig, segment: str) -> None:
    base = f"https://{apex}/{segment}/{_PUBLIC_PREFIX}/webhooks"
    if brand.telegram is not None and brand.telegram.enabled:
        provider = TelegramContactProvider(brand.telegram)
        if brand.telegram.polling_enabled:
            await provider.delete_webhook()
            logger.info("customer_auth.webhook.polling", apex=apex, provider="telegram")
        else:
            await provider.set_webhook(
                f"{base}/telegram", brand.telegram.webhook_secret
            )
            logger.info("customer_auth.webhook.set", apex=apex, provider="telegram")
    if brand.max is not None and brand.max.enabled:
        provider = MaxContactProvider(brand.max)
        await provider.set_webhook(f"{base}/max", brand.max.webhook_secret)
        logger.info("customer_auth.webhook.set", apex=apex, provider="max")


async def main(service_segment: str) -> None:
    brands = get_settings().customer_auth.brands
    if not brands:
        raise SystemExit("customer_auth.brands is empty — nothing to sync")
    for apex, brand in brands.items():
        await _sync_brand(apex, brand, service_segment)


class _Args(argparse.Namespace):
    def __init__(self) -> None:
        super().__init__()
        self.service_segment: str = "shop"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    _ = parser.add_argument(
        "--service-segment",
        default="shop",
        help="сервисный сегмент webhook-URL (по умолчанию shop)",
    )
    args = parser.parse_args(namespace=_Args())
    asyncio.run(main(args.service_segment))

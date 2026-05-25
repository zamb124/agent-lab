"""
Telegram Dev Polling - корутина для polling в dev окружении.

В production Telegram шлёт updates через webhook.
В dev localhost недоступен для setWebhook - используем getUpdates, затем POST на тот же
HTTP-эндпоинт, что и в проде: /flows/api/v1/triggers/telegram/{flow_id}/{trigger_id}.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass

from apps.flows.config import get_settings
from apps.flows.src.container import FlowContainer, get_container
from apps.flows.src.models import (
    TelegramBotApiBooleanResponse,
    TelegramGetUpdatesResponse,
    TelegramTriggerConfig,
    TelegramUpdate,
    TriggerType,
)
from apps.flows.src.triggers.config_var_resolve import resolve_at_var_for_flow
from apps.flows.src.triggers.handlers.base import TriggerRegistrationError
from apps.flows.src.triggers.handlers.telegram import TelegramTriggerHandler
from apps.flows.src.triggers.verify_draft import normalize_telegram_bot_token_for_api
from core.context import clear_context, set_context
from core.http import ProxyStrategy, get_httpx_client
from core.http.client import SmartProxyClient
from core.logging import get_logger
from core.models import Company, Context, User
from core.types import JsonObject, JsonValue, require_json_object

logger = get_logger(__name__)

TelegramPollingHandler = Callable[[str, str, JsonObject, str], Awaitable[None]]


@dataclass(frozen=True)
class TelegramPollingTrigger:
    flow_id: str
    trigger_id: str
    bot_token: str
    subdomain: str
    trigger_config: TelegramTriggerConfig


class TelegramPollingBot:
    """Polling для одного Telegram бота."""

    def __init__(
        self,
        flow_id: str,
        trigger_id: str,
        bot_token: str,
        subdomain: str,
        handler_callback: TelegramPollingHandler,
        allowed_updates: list[str],
    ) -> None:
        self.flow_id: str = flow_id
        self.trigger_id: str = trigger_id
        self.bot_token: str = bot_token
        self.subdomain: str = subdomain
        self.handler_callback: TelegramPollingHandler = handler_callback
        self.allowed_updates: list[str] = allowed_updates
        self.offset: int = 0
        self.running: bool = False

    @property
    def bot_key(self) -> str:
        return f"{self.flow_id}:{self.trigger_id}"

    async def delete_webhook(self) -> None:
        """Удаляет webhook перед polling."""
        url = f"{get_settings().telegram.api_base}/bot{self.bot_token}/deleteWebhook"
        async with get_httpx_client(timeout=10.0, strategy=ProxyStrategy.SMART) as client:
            response = await client.post(url)

        if response.status_code != 200:
            raise RuntimeError(
                f"[{self.bot_key}] deleteWebhook failed: {response.status_code} {response.text}"
            )

        result = TelegramBotApiBooleanResponse.model_validate_json(response.content)
        if not result.ok:
            description = result.description or "Telegram API returned ok=false"
            raise RuntimeError(f"[{self.bot_key}] deleteWebhook failed: {description}")

        logger.info(f"[{self.bot_key}] Webhook deleted")

    async def get_updates(self, client: SmartProxyClient) -> list[TelegramUpdate]:
        """Long polling getUpdates."""
        response = await client.get(
            f"{get_settings().telegram.api_base}/bot{self.bot_token}/getUpdates",
            params={
                "offset": self.offset,
                "timeout": 30,
                "allowed_updates": self.allowed_updates,
            },
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"[{self.bot_key}] Telegram getUpdates failed: {response.status_code} {response.text}"
            )

        data = TelegramGetUpdatesResponse.model_validate_json(response.content)
        if not data.ok:
            description = data.description or "Telegram API returned ok=false"
            raise RuntimeError(f"[{self.bot_key}] Telegram getUpdates failed: {description}")
        if data.result is None:
            raise RuntimeError(f"[{self.bot_key}] Telegram getUpdates result is missing")
        return data.result

    async def run(self) -> None:
        """Основной цикл polling."""
        self.running = True

        await self.delete_webhook()

        logger.info(f"[{self.bot_key}] Polling started (token: ...{self.bot_token[-8:]})")

        async with get_httpx_client(timeout=35.0, strategy=ProxyStrategy.SMART) as client:
            while self.running:
                updates = await self.get_updates(client)

                for update in updates:
                    self.offset = update.update_id + 1

                    text_preview = ""
                    chat_id: JsonValue = None
                    message = update.message
                    if message is not None:
                        text_raw = message.get("text")
                        if isinstance(text_raw, str):
                            text_preview = text_raw[:30]
                        chat_raw = message.get("chat")
                        if chat_raw is not None:
                            chat = require_json_object(chat_raw, "telegram.message.chat")
                            chat_id = chat.get("id")

                    logger.info(
                        "[%s] Update %s: chat=%s, text='%s...'",
                        self.bot_key,
                        update.update_id,
                        chat_id,
                        text_preview,
                    )

                    await self.handler_callback(
                        self.flow_id,
                        self.trigger_id,
                        update.to_payload(),
                        self.subdomain,
                    )

        logger.info(f"[{self.bot_key}] Polling stopped")

    def stop(self) -> None:
        self.running = False


class TelegramDevPolling:
    """
    Менеджер dev polling для всех Telegram триггеров.

    Запускается при старте сервера в dev режиме.
    Периодически сканирует агентов и запускает/останавливает polling боты.
    """

    def __init__(self) -> None:
        self.bots: dict[str, TelegramPollingBot] = {}
        self.bot_tasks: dict[str, asyncio.Task[None]] = {}
        self.running: bool = False
        self._task: asyncio.Task[None] | None = None
        self._scan_interval: int = 10

    async def _resolve_company_for_subdomain(
        self,
        container: FlowContainer,
        subdomain: str,
    ) -> Company:
        company_id = await container.subdomain_repository.get_company_id(subdomain)
        if company_id:
            company = await container.company_repository.get(company_id)
            if company is not None:
                return company

        company = await container.company_repository.get(subdomain)
        if company is not None:
            return company

        raise RuntimeError(f"Dev polling company not found for identifier {subdomain!r}")

    async def _get_telegram_triggers(self) -> list[TelegramPollingTrigger]:
        """Собирает все Telegram триггеры из агентов всех компаний."""
        triggers: list[TelegramPollingTrigger] = []
        container = get_container()

        subdomains = await container.flow_repository.list_company_identifiers()
        logger.info(f"Scanning subdomains: {subdomains}")

        for subdomain in subdomains:
            company = await self._resolve_company_for_subdomain(container, subdomain)
            dev_user = User(
                user_id="system",
                name="System",
                groups=["admin"],
                companies={company.company_id: ["admin"]},
                active_company_id=company.company_id,
            )
            context = Context(
                user=dev_user,
                active_company=company,
                user_companies=[company],
                channel="system",
            )
            set_context(context)
            try:
                all_flows = await container.flow_repository.list(limit=10_000)
                logger.info(f"[{subdomain}] Found {len(all_flows)} flows")

                for flow_cfg in all_flows:
                    for trigger_id, trigger in flow_cfg.triggers.items():
                        logger.info(
                            "[%s:%s:%s] type=%s, enabled=%s",
                            subdomain,
                            flow_cfg.flow_id,
                            trigger_id,
                            trigger.type.value,
                            trigger.enabled,
                        )
                        if trigger.type != TriggerType.TELEGRAM or not trigger.enabled:
                            continue

                        config = TelegramTriggerConfig.model_validate(trigger.config)
                        raw_bot_token = config.bot_token
                        if raw_bot_token is None or not raw_bot_token.strip():
                            raise TriggerRegistrationError(
                                trigger_type="telegram",
                                flow_id=flow_cfg.flow_id,
                                trigger_id=trigger_id,
                                message="bot_token is required for dev polling",
                            )
                        bot_token_ref = raw_bot_token.strip()
                        if bot_token_ref.startswith("@var:"):
                            bot_token_ref = await resolve_at_var_for_flow(
                                container.flow_factory,
                                flow_cfg.flow_id,
                                bot_token_ref,
                                branch_id=trigger.branch_id,
                            )
                        bot_token = normalize_telegram_bot_token_for_api(bot_token_ref)
                        if not bot_token:
                            raise TriggerRegistrationError(
                                trigger_type="telegram",
                                flow_id=flow_cfg.flow_id,
                                trigger_id=trigger_id,
                                message="bot_token is empty after resolve",
                            )

                        logger.info(
                            "[%s:%s] Found telegram trigger with token ...%s",
                            flow_cfg.flow_id,
                            trigger_id,
                            bot_token[-8:],
                        )
                        triggers.append(
                            TelegramPollingTrigger(
                                flow_id=flow_cfg.flow_id,
                                trigger_id=trigger_id,
                                bot_token=bot_token,
                                subdomain=subdomain,
                                trigger_config=config,
                            )
                        )
            finally:
                clear_context()

        return triggers

    async def _handle_update(
        self,
        flow_id: str,
        trigger_id: str,
        payload: JsonObject,
        subdomain: str,
    ) -> None:
        """
        Пробрасывает Update в тот же POST /flows/api/v1/triggers/telegram/.../...,
        что обрабатывает внешний Telegram в production (AuthMiddleware, хендлер, executor).
        """
        _ = subdomain

        settings = get_settings()
        base = settings.server.get_service_url("flows").rstrip("/")
        svc = settings.server.name
        path = f"/{svc}/api/v1/triggers/telegram/{flow_id}/{trigger_id}"
        url = f"{base}{path}"

        container = get_container()
        unscoped = await container.flow_repository.get_latest_by_flow_id_unscoped(flow_id)
        if unscoped is None:
            raise RuntimeError(f"Dev polling flow not found for unscoped flow_id={flow_id!r}")

        flow_config, _company_identifier = unscoped
        trigger = flow_config.triggers.get(trigger_id)
        if trigger is None:
            raise RuntimeError(
                f"Dev polling trigger not found: flow_id={flow_id!r}, trigger_id={trigger_id!r}"
            )
        config = TelegramTriggerConfig.model_validate(trigger.config)
        secret = config.internal_secret_token
        if secret is None or not secret.strip():
            message = (
                f"Dev polling trigger secret is missing: flow_id={flow_id!r}, "
                f"trigger_id={trigger_id!r}"
            )
            raise RuntimeError(
                message
            )

        headers = {"X-Telegram-Bot-Api-Secret-Token": secret}

        async with get_httpx_client(timeout=120.0, strategy=ProxyStrategy.SMART) as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code >= 400:
            raise RuntimeError(
                f"Dev polling POST {path} failed: {response.status_code} {response.text[:500]}"
            )

        logger.debug(f"Dev polling POST {path} ok: {response.status_code} {response.text[:200]}")

    async def _sync_bots(self) -> None:
        """Синхронизирует polling боты с текущими триггерами."""
        triggers = await self._get_telegram_triggers()

        current_keys: set[str] = set()

        for trigger_data in triggers:
            key = f"{trigger_data.flow_id}:{trigger_data.trigger_id}"
            task = self.bot_tasks.get(key)
            if task is not None and task.done():
                _ = task.result()

            allowed_updates = TelegramTriggerHandler.normalize_allowed_updates(
                trigger_data.flow_id,
                trigger_data.trigger_id,
                trigger_data.trigger_config,
            )

            current_keys.add(key)

            if key not in self.bots:
                bot = TelegramPollingBot(
                    flow_id=trigger_data.flow_id,
                    trigger_id=trigger_data.trigger_id,
                    bot_token=trigger_data.bot_token,
                    subdomain=trigger_data.subdomain,
                    handler_callback=self._handle_update,
                    allowed_updates=allowed_updates,
                )
                self.bots[key] = bot
                self.bot_tasks[key] = asyncio.create_task(bot.run())
                logger.info(f"Started polling bot: {key}")

        for key in list(self.bots.keys()):
            if key not in current_keys:
                self.bots[key].stop()
                task = self.bot_tasks.pop(key)
                _ = task.cancel()
                del self.bots[key]
                logger.info(f"Stopped polling bot: {key}")

    async def run(self) -> None:
        """Основной цикл сканирования."""
        self.running = True

        logger.info("=" * 50)
        logger.info("Telegram Dev Polling started")
        logger.info("=" * 50)

        try:
            while self.running:
                await self._sync_bots()
                await asyncio.sleep(self._scan_interval)
        finally:
            for bot in self.bots.values():
                bot.stop()
            for task in self.bot_tasks.values():
                _ = task.cancel()
            for task in self.bot_tasks.values():
                with suppress(asyncio.CancelledError):
                    await task
            self.bots.clear()
            self.bot_tasks.clear()

        logger.info("Telegram Dev Polling stopped")

    def start(self) -> asyncio.Task[None]:
        """Запускает polling в background."""
        current = self._task
        if current is not None and not current.done():
            return current
        self._task = asyncio.create_task(self.run())
        return self._task

    def stop(self) -> None:
        """Останавливает polling."""
        self.running = False
        for bot in self.bots.values():
            bot.stop()
        if self._task:
            _ = self._task.cancel()


_dev_polling: TelegramDevPolling | None = None


def get_dev_polling() -> TelegramDevPolling:
    global _dev_polling
    if _dev_polling is None:
        _dev_polling = TelegramDevPolling()
    return _dev_polling


async def start_dev_polling() -> None:
    """Запускает dev polling если в dev окружении."""
    settings = get_settings()

    if settings.server.env != "development":
        logger.info("Not in development mode, skipping Telegram dev polling")
        return

    polling = get_dev_polling()
    _ = polling.start()
    logger.info("Telegram dev polling task started")


async def stop_dev_polling() -> None:
    """Останавливает dev polling."""
    global _dev_polling
    if _dev_polling:
        _dev_polling.stop()
        _dev_polling = None

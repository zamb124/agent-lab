"""
Telegram Long Polling для локальной разработки.
Запускается только если ENV=local.
"""

import logging
import asyncio
import traceback
import json
from typing import Dict, List
import httpx

from app.core.storage import Storage
from app.interfaces.telegram_interface import TelegramInterface
from app.core.config import settings
from app.models import FlowConfig

logger = logging.getLogger(__name__)


class TelegramPoller:
    """
    Long polling для всех Telegram ботов в локальной разработке.
    """

    def __init__(self):
        self.active_bots: Dict[str, Dict] = {}  # {username: {token, flow_id, offset}}
        self.polling_tasks: List[asyncio.Task] = []
        self.running = False

    async def start(self):
        """Запускает long polling для всех ботов"""
        if self.running:
            return

        self.running = True
        logger.info("🔄 Запуск Telegram long polling...")

        # Находим всех ботов в БД
        await self._discover_bots()

        # Запускаем polling для каждого бота
        for username, bot_data in self.active_bots.items():
            task = asyncio.create_task(self._poll_bot(username, bot_data))
            self.polling_tasks.append(task)
            logger.info(f"🤖 Запущен polling для @{username}")

    async def stop(self):
        """Останавливает все polling tasks"""
        self.running = False

        # Отменяем все задачи
        for task in self.polling_tasks:
            task.cancel()

        # Ждем завершения
        if self.polling_tasks:
            await asyncio.gather(*self.polling_tasks, return_exceptions=True)

        self.polling_tasks.clear()
        logger.info("🛑 Telegram long polling остановлен")

    async def _discover_bots(self):
        """Находит всех ботов с токенами в БД"""
        storage = Storage()

        # Получаем все flows динамически - ищем во всех компаниях
        all_keys = await storage.list_by_prefix("", 1000, force_global=True)
        flow_keys = [key for key in all_keys if ":flow:" in key]
        
        for flow_key in flow_keys:
            try:
                # Получаем данные флоу прямо по ключу
                flow_data = await storage.get(flow_key, force_global=True)
                if not flow_data:
                    continue
                
                flow_config = FlowConfig.model_validate_json(flow_data)
                flow_id = flow_config.flow_id

                telegram_config = flow_config.platforms.get("telegram")
                if not telegram_config:
                    continue

                username = telegram_config.get("username")
                if not username:
                    continue

                # Получаем токен из БД
                token = await TelegramInterface.get_bot_token_for_flow(
                    flow_id, telegram_config
                )
                if not token:
                    continue

                self.active_bots[username] = {
                    "token": token,
                    "flow_id": flow_id,
                    "offset": 0,
                    "platform_config": telegram_config,
                }

                # Устанавливаем команды для бота
                try:
                    telegram_interface = TelegramInterface(token, telegram_config)
                    await telegram_interface.setup_commands()
                    logger.info(f"✅ Команды установлены для @{username}")
                except Exception as cmd_error:
                    logger.warning(
                        f"⚠️ Не удалось установить команды для @{username}: {cmd_error}"
                    )

                logger.info(f"🔍 Найден бот @{username} для flow {flow_id}")

            except Exception as e:
                logger.error(f"Ошибка обработки flow {flow_id}: {e}")
                logger.error(f"Тип ошибки: {type(e).__name__}")
                logger.error(f"Traceback: {traceback.format_exc()}")

    async def _poll_bot(self, username: str, bot_data: Dict):
        """Long polling для одного бота"""
        token = bot_data["token"]
        flow_id = bot_data["flow_id"]
        offset = bot_data["offset"]
        platform_config = bot_data["platform_config"]

        logger.info(f"🔄 Начинаем polling для @{username} (flow: {flow_id})")

        while self.running:
            try:
                # Получаем обновления от Telegram
                url = f"https://api.telegram.org/bot{token}/getUpdates"
                params = {
                    "offset": offset,
                    "timeout": 30,  # Long polling 30 секунд
                    "allowed_updates": ["message"],
                }

                async with httpx.AsyncClient(timeout=35.0) as client:
                    response = await client.get(url, params=params)

                    if response.status_code != 200:
                        logger.error(
                            f"❌ Ошибка Telegram API для @{username}: {response.status_code}"
                        )
                        await asyncio.sleep(5)
                        continue

                    data = response.json()
                    updates = data.get("result", [])

                    if not updates:
                        continue  # Нет новых сообщений

                    # Обрабатываем каждое обновление
                    for update in updates:
                        try:
                            await self._process_update(
                                update, flow_id, platform_config, token
                            )
                            offset = max(offset, update["update_id"] + 1)
                        except Exception as e:
                            logger.error(
                                f"Ошибка обработки update {update.get('update_id')}: {e}"
                            )

                    # Обновляем offset
                    bot_data["offset"] = offset

            except asyncio.CancelledError:
                logger.info(f"🛑 Polling для @{username} отменен")
                break
            except Exception as e:
                logger.error(f"Ошибка polling для @{username}: {e}")
                logger.error(f"Тип ошибки: {type(e).__name__}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                await asyncio.sleep(5)  # Пауза при ошибке

    async def _process_update(
        self, update: Dict, flow_id: str, platform_config: Dict, token: str
    ):
        """Обрабатывает одно обновление от Telegram через webhook endpoint"""
        try:
            # Отправляем update в наш webhook endpoint (эмуляция webhook)
            webhook_url = (
                f"http://localhost:{settings.port}/api/v1/webhook/telegram/{flow_id}"
            )

            async with httpx.AsyncClient() as client:
                response = await client.post(webhook_url, json=update)

                if response.status_code == 200:
                    logger.info(
                        f"📋 Long polling: update {update.get('update_id')} отправлен в webhook"
                    )
                else:
                    logger.error(
                        f"❌ Ошибка отправки в webhook: {response.status_code}"
                    )

        except Exception as e:
            logger.error(f"Ошибка отправки update в webhook: {e}")


# Глобальный экземпляр
telegram_poller = TelegramPoller()

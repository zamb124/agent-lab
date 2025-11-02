"""
Telegram Long Polling для локальной разработки.
Запускается только если ENV=local.
"""

import logging
import asyncio
import traceback
from typing import Dict, List
import httpx

from app.core.config import settings
from app.models import FlowConfig
from app.core.container import get_container
from app.services.variables_service import get_variables_service
from app.core.context import set_context
from app.models import Context
from app.identity.models import User, AuthProvider, UserStatus, Company
from app.models.i18n_models import Language

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

    async def reload(self):
        """Перезагружает список ботов без полной остановки сервиса"""
        logger.info("🔄 Перезагрузка Telegram ботов...")

        # Останавливаем текущие polling tasks
        for task in self.polling_tasks:
            task.cancel()

        if self.polling_tasks:
            await asyncio.gather(*self.polling_tasks, return_exceptions=True)

        self.polling_tasks.clear()

        # Сохраняем старые офсеты
        old_offsets = {username: bot_data["offset"] for username, bot_data in self.active_bots.items()}

        # Очищаем список ботов
        self.active_bots.clear()

        # Заново ищем ботов
        await self._discover_bots()

        # Восстанавливаем офсеты для существующих ботов
        for username, bot_data in self.active_bots.items():
            if username in old_offsets:
                bot_data["offset"] = old_offsets[username]

        # Запускаем polling для всех ботов
        for username, bot_data in self.active_bots.items():
            task = asyncio.create_task(self._poll_bot(username, bot_data))
            self.polling_tasks.append(task)
            logger.info(f"🤖 Запущен polling для @{username}")

        logger.info(f"✅ Перезагрузка завершена. Активных ботов: {len(self.active_bots)}")

    async def _discover_bots(self):
        """Находит всех ботов с токенами в БД"""
        storage = get_container().storage

        # Получаем все flows динамически - ищем во всех компаниях
        all_keys = await storage.list_by_prefix("", 1000, force_global=True)
        flow_keys = [key for key in all_keys if ":flow:" in key]

        for flow_key in flow_keys:
            flow_data = await storage.get(flow_key, force_global=True)
            if not flow_data:
                continue

            flow_config = FlowConfig.model_validate_json(flow_data)
            flow_id = flow_config.flow_id

            telegram_config = flow_config.platforms.get("telegram")
            if not telegram_config:
                continue

            # Резолвим весь telegram_config (username и token могут быть @var:key)
            # Создаем контекст для резолюции
            company_id = flow_key.split(":")[1] if ":" in flow_key else "system"
            company_data = await storage.get(f"company:{company_id}", force_global=True)
            if not company_data:
                continue

            company = Company.model_validate_json(company_data)
            user = User(
                user_id="system",
                provider=AuthProvider.YANDEX,
                provider_user_id="system",
                email="",
                name="System",
                status=UserStatus.ACTIVE,
                groups=["system"],
                companies={company_id: ["admin"]},
                active_company_id=company_id
            )
            context = Context(
                user=user,
                platform="telegram",
                active_company=company,
                user_companies=[company],
                language=Language.RU
            )
            set_context(context)

            # Резолвим telegram_config
            variables_service = get_container().variables_service
            resolved_config = await variables_service.resolve(telegram_config, auto_create=True)

            username = resolved_config.get("username")
            token = resolved_config.get("token")

            if not username:
                logger.warning(f"⚠️ Flow {flow_id} не имеет username после резолюции")
                continue

            if not token:
                logger.warning(f"⚠️ Flow {flow_id} не имеет token после резолюции")
                continue

            logger.info(f"✅ Резолвнуто: username={username}, token={'***'}")

            self.active_bots[username] = {
                "token": token,
                "flow_key": flow_key,
                "flow_id": flow_id,
                "offset": 0,
                "platform_config": telegram_config,
            }

            logger.info(f"🔍 Найден бот @{username} для {flow_key}")

    async def _poll_bot(self, username: str, bot_data: Dict):
        """Long polling для одного бота"""
        token = bot_data["token"]
        flow_key = bot_data["flow_key"]
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
                        await self._process_update(
                            update, flow_key, platform_config, token
                        )
                        offset = max(offset, update["update_id"] + 1)

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
        self, update: Dict, flow_key: str, platform_config: Dict, token: str
    ):
        """Обрабатывает одно обновление от Telegram через webhook endpoint"""
        webhook_url = f"http://127.0.0.1:{settings.server.port}/api/v1/webhook/telegram/{flow_key}"
        update_id = update.get('update_id', 'unknown')

        logger.info(f"📤 Отправка update {update_id} в webhook: {webhook_url}")

        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            response = await client.post(webhook_url, json=update)

            if response.status_code == 200:
                logger.info(f"✅ Update {update_id} успешно обработан")
            else:
                logger.error(f"❌ Ошибка webhook: {response.status_code}")
                logger.error(f"❌ URL: {webhook_url}")
                logger.error(f"❌ Ответ: {response.text}")
                logger.error(f"❌ Update ID: {update_id}")


# Глобальный экземпляр
telegram_poller = TelegramPoller()

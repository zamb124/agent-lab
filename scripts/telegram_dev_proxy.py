"""
Telegram Dev Proxy - polling сервис для development окружения.

Проблема: В dev окружении localhost недоступен из интернета,
поэтому Telegram не может отправлять webhooks.

Решение: Этот скрипт:
1. Загружает все агенты с Telegram триггерами из БД
2. Для каждого триггера запускает polling через getUpdates
3. При получении update вызывает локальную ручку trigger

Запуск:
    uv run python scripts/telegram_dev_proxy.py

Или через make:
    make telegram-dev
"""

import asyncio
import signal
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import get_settings
from core.logging import get_logger, setup_logging

setup_logging("telegram-dev-proxy")
logger = get_logger(__name__)


class TelegramPollingBot:
    """Polling бот для одного Telegram триггера."""
    
    def __init__(
        self,
        flow_id: str,
        trigger_id: str,
        bot_token: str,
        secret_token: Optional[str],
        local_url: str,
    ):
        self.flow_id = flow_id
        self.trigger_id = trigger_id
        self.bot_token = bot_token
        self.secret_token = secret_token
        self.local_url = local_url
        self.offset = 0
        self.running = False
        self._task: Optional[asyncio.Task] = None
        
    @property
    def trigger_url(self) -> str:
        return f"{self.local_url}/flows/api/v1/triggers/telegram/{self.flow_id}/{self.trigger_id}"
    
    @property
    def telegram_api_url(self) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}"
    
    async def get_updates(self, client: httpx.AsyncClient) -> List[Dict[str, Any]]:
        """Получает updates через long polling."""
        try:
            response = await client.get(
                f"{self.telegram_api_url}/getUpdates",
                params={
                    "offset": self.offset,
                    "timeout": 30,
                    "allowed_updates": ["message", "callback_query"],
                },
                timeout=35.0,
            )
            
            if response.status_code != 200:
                logger.error(f"[{self.flow_id}/{self.trigger_id}] Telegram API error: {response.text}")
                return []
            
            data = response.json()
            if not data.get("ok"):
                logger.error(f"[{self.flow_id}/{self.trigger_id}] Telegram API error: {data}")
                return []
            
            return data.get("result", [])
            
        except httpx.TimeoutException:
            return []
        except Exception as e:
            logger.error(f"[{self.flow_id}/{self.trigger_id}] Error getting updates: {e}")
            return []
    
    async def forward_update(self, client: httpx.AsyncClient, update: Dict[str, Any]) -> bool:
        """Пересылает update в локальную ручку триггера."""
        try:
            headers = {}
            if self.secret_token:
                headers["X-Telegram-Bot-Api-Secret-Token"] = self.secret_token
            
            response = await client.post(
                self.trigger_url,
                json=update,
                headers=headers,
                timeout=30.0,
            )
            
            if response.status_code == 200:
                logger.info(
                    f"[{self.flow_id}/{self.trigger_id}] "
                    f"Update {update['update_id']} forwarded successfully"
                )
                return True
            else:
                logger.error(
                    f"[{self.flow_id}/{self.trigger_id}] "
                    f"Failed to forward update: {response.status_code} - {response.text}"
                )
                return False
                
        except Exception as e:
            logger.error(f"[{self.flow_id}/{self.trigger_id}] Error forwarding update: {e}")
            return False
    
    async def run(self):
        """Основной цикл polling."""
        self.running = True
        logger.info(
            f"[{self.flow_id}/{self.trigger_id}] "
            f"Starting polling for bot token ...{self.bot_token[-8:]}"
        )
        
        # Удаляем webhook если был
        async with httpx.AsyncClient() as client:
            await client.post(f"{self.telegram_api_url}/deleteWebhook")
        
        async with httpx.AsyncClient() as client:
            while self.running:
                updates = await self.get_updates(client)
                
                for update in updates:
                    update_id = update.get("update_id", 0)
                    
                    # Обновляем offset сразу
                    self.offset = update_id + 1
                    
                    # Логируем что получили
                    message = update.get("message", {})
                    text = message.get("text", "")[:50] if message else ""
                    chat_id = message.get("chat", {}).get("id") if message else None
                    logger.info(
                        f"[{self.flow_id}/{self.trigger_id}] "
                        f"Received update {update_id}: chat={chat_id}, text='{text}...'"
                    )
                    
                    # Пересылаем в локальный сервер
                    await self.forward_update(client, update)
        
        logger.info(f"[{self.flow_id}/{self.trigger_id}] Polling stopped")
    
    def start(self) -> asyncio.Task:
        """Запускает polling в background task."""
        self._task = asyncio.create_task(self.run())
        return self._task
    
    def stop(self):
        """Останавливает polling."""
        self.running = False
        if self._task:
            self._task.cancel()


class TelegramDevProxy:
    """Менеджер для всех Telegram polling ботов."""
    
    def __init__(self, local_url: str = "http://localhost:8000"):
        self.local_url = local_url
        self.bots: List[TelegramPollingBot] = []
        self.running = False
    
    async def load_telegram_triggers(self) -> List[Dict[str, Any]]:
        """Загружает все Telegram триггеры из БД."""
        from apps.flows.src.container import get_container
        
        container = get_container()
        await container.initialize()
        
        triggers = []
        
        # Получаем все агенты
        agents = await container.flow_repository.list(limit=10000)
        
        for agent in agents:
            if not agent.triggers:
                continue
            
            for trigger_id, trigger in agent.triggers.items():
                if trigger.type.value == "telegram":
                    bot_token = trigger.config.get("bot_token", "")
                    
                    # Резолвим @var: ссылки
                    if bot_token.startswith("@var:"):
                        var_name = bot_token[5:]
                        bot_token = agent.variables.get(var_name, "")
                    
                    if not bot_token:
                        logger.warning(
                            f"Agent {agent.flow_id} trigger {trigger_id}: "
                            f"bot_token not found"
                        )
                        continue
                    
                    triggers.append({
                        "flow_id": agent.flow_id,
                        "trigger_id": trigger_id,
                        "bot_token": bot_token,
                        "secret_token": trigger.config.get("secret_token"),
                    })
                    
                    logger.info(
                        f"Found Telegram trigger: {agent.flow_id}/{trigger_id} "
                        f"(token: ...{bot_token[-8:]})"
                    )
        
        await container.close()
        
        return triggers
    
    async def run(self):
        """Запускает proxy."""
        self.running = True
        
        logger.info("=" * 60)
        logger.info("Telegram Dev Proxy starting...")
        logger.info(f"Local server URL: {self.local_url}")
        logger.info("=" * 60)
        
        # Загружаем триггеры
        triggers = await self.load_telegram_triggers()
        
        if not triggers:
            logger.warning("No Telegram triggers found in any agent")
            return
        
        logger.info(f"Found {len(triggers)} Telegram trigger(s)")
        
        # Создаём боты для каждого триггера
        for trigger_data in triggers:
            bot = TelegramPollingBot(
                flow_id=trigger_data["flow_id"],
                trigger_id=trigger_data["trigger_id"],
                bot_token=trigger_data["bot_token"],
                secret_token=trigger_data["secret_token"],
                local_url=self.local_url,
            )
            self.bots.append(bot)
        
        # Запускаем все боты
        tasks = [bot.start() for bot in self.bots]
        
        logger.info(f"Started {len(tasks)} polling bot(s)")
        logger.info("Press Ctrl+C to stop")
        
        # Ждём завершения
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.CancelledError:
            pass
    
    def stop(self):
        """Останавливает все боты."""
        self.running = False
        for bot in self.bots:
            bot.stop()
        logger.info("All bots stopped")


async def main():
    settings = get_settings()
    
    # URL локального сервера
    local_url = f"http://localhost:{settings.server.port}"
    
    proxy = TelegramDevProxy(local_url=local_url)
    
    # Обработка сигналов для graceful shutdown
    loop = asyncio.get_event_loop()
    
    def signal_handler():
        logger.info("Received shutdown signal")
        proxy.stop()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    await proxy.run()


if __name__ == "__main__":
    asyncio.run(main())

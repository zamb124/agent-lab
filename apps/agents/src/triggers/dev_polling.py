"""
Telegram Dev Polling - корутина для polling в dev окружении.

В production Telegram шлёт updates через webhook.
В dev localhost недоступен - используем polling через getUpdates.
"""

import asyncio
from typing import Any, Dict, List, Optional, Set

import httpx

from core.config import get_settings
from core.http import get_httpx_client
from core.logging import get_logger

logger = get_logger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramPollingBot:
    """Polling для одного Telegram бота."""
    
    def __init__(
        self,
        agent_id: str,
        trigger_id: str,
        bot_token: str,
        subdomain: str,
        handler_callback,
    ):
        self.agent_id = agent_id
        self.trigger_id = trigger_id
        self.bot_token = bot_token
        self.subdomain = subdomain
        self.handler_callback = handler_callback
        self.offset = 0
        self.running = False
    
    @property
    def bot_key(self) -> str:
        return f"{self.agent_id}:{self.trigger_id}"
    
    async def delete_webhook(self):
        """Удаляет webhook перед polling."""
        url = f"{TELEGRAM_API_BASE}/bot{self.bot_token}/deleteWebhook"
        try:
            async with get_httpx_client(timeout=10.0, proxy=True) as client:
                await client.post(url)
                logger.info(f"[{self.bot_key}] Webhook deleted")
        except Exception as e:
            logger.warning(f"[{self.bot_key}] Failed to delete webhook: {e}")
    
    async def get_updates(self, client) -> List[Dict[str, Any]]:
        """Long polling getUpdates."""
        try:
            response = await client.get(
                f"{TELEGRAM_API_BASE}/bot{self.bot_token}/getUpdates",
                params={
                    "offset": self.offset,
                    "timeout": 30,
                    "allowed_updates": ["message", "callback_query"],
                },
                timeout=35.0,
            )
            
            if response.status_code != 200:
                logger.error(f"[{self.bot_key}] API error: {response.text}")
                return []
            
            data = response.json()
            if not data.get("ok"):
                logger.error(f"[{self.bot_key}] API error: {data}")
                return []
            
            return data.get("result", [])
            
        except httpx.TimeoutException:
            return []
        except Exception as e:
            logger.error(f"[{self.bot_key}] getUpdates error: {e}")
            await asyncio.sleep(5)
            return []
    
    async def run(self):
        """Основной цикл polling."""
        self.running = True
        
        await self.delete_webhook()
        
        logger.info(f"[{self.bot_key}] Polling started (token: ...{self.bot_token[-8:]})")
        
        async with get_httpx_client(proxy=True) as client:
            while self.running:
                updates = await self.get_updates(client)
                
                for update in updates:
                    update_id = update.get("update_id", 0)
                    self.offset = update_id + 1
                    
                    message = update.get("message", {})
                    text = message.get("text", "")[:30] if message else ""
                    chat_id = message.get("chat", {}).get("id") if message else None
                    
                    logger.info(
                        f"[{self.bot_key}] Update {update_id}: "
                        f"chat={chat_id}, text='{text}...'"
                    )
                    
                    try:
                        await self.handler_callback(
                            self.agent_id,
                            self.trigger_id,
                            update,
                            self.subdomain,
                        )
                    except Exception as e:
                        logger.error(f"[{self.bot_key}] Handler error: {e}")
        
        logger.info(f"[{self.bot_key}] Polling stopped")
    
    def stop(self):
        self.running = False


class TelegramDevPolling:
    """
    Менеджер dev polling для всех Telegram триггеров.
    
    Запускается при старте сервера в dev режиме.
    Периодически сканирует агенты и запускает/останавливает polling боты.
    """
    
    def __init__(self):
        self.bots: Dict[str, TelegramPollingBot] = {}
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._scan_interval = 10  # секунд между сканированиями
    
    async def _get_telegram_triggers(self) -> List[Dict[str, Any]]:
        """Собирает все Telegram триггеры из агентов всех компаний."""
        from apps.agents.src.container import get_container
        from core.context import set_context, clear_context
        from core.models import Context, Company, User
        
        triggers = []
        container = get_container()
        
        # Получаем все subdomains из БД напрямую
        subdomains = await self._get_all_subdomains(container)
        logger.info(f"Scanning subdomains: {subdomains}")
        
        try:
            dev_user = User(user_id="system", email="system@dev.local", name="System")
        except Exception as e:
            logger.error(f"Failed to create User: {e}", exc_info=True)
            return triggers
        
        for subdomain in subdomains:
            logger.info(f"Processing subdomain: {subdomain}")
            try:
                # Устанавливаем контекст для каждой компании
                company = Company(
                    company_id=subdomain,
                    subdomain=subdomain,
                    name=f"{subdomain} Company",
                )
                context = Context(
                    user=dev_user,
                    active_company=company,
                    user_companies=[company],
                    channel="system",
                )
                set_context(context)
                
                logger.info(f"[{subdomain}] Calling list_all()...")
                try:
                    agents = await asyncio.wait_for(
                        container.agent_repository.list_all(),
                        timeout=10.0
                    )
                    logger.info(f"[{subdomain}] Found {len(agents)} agents")
                except asyncio.TimeoutError:
                    logger.error(f"[{subdomain}] list_all() timeout!")
                    continue
                except Exception as e:
                    logger.error(f"[{subdomain}] list_all() failed: {e}", exc_info=True)
                    continue
                
                for agent in agents:
                    if not agent.triggers:
                        logger.debug(f"[{subdomain}:{agent.agent_id}] No triggers")
                        continue
                    
                    logger.info(f"[{subdomain}:{agent.agent_id}] Has {len(agent.triggers)} triggers: {list(agent.triggers.keys())}")
                    
                    for trigger_id, trigger in agent.triggers.items():
                        trigger_type = trigger.type.value if hasattr(trigger.type, 'value') else str(trigger.type)
                        logger.info(f"[{subdomain}:{agent.agent_id}:{trigger_id}] type={trigger_type}, enabled={trigger.enabled}")
                        if trigger_type != "telegram" or not trigger.enabled:
                            continue
                        
                        bot_token = trigger.config.get("bot_token", "")
                        
                        # Резолвим @var:
                        if bot_token.startswith("@var:"):
                            var_name = bot_token[5:]
                            var_config = agent.variables.get(var_name)
                            if var_config is None:
                                bot_token = ""
                            elif isinstance(var_config, dict):
                                bot_token = var_config.get("value", "")
                            elif hasattr(var_config, 'value'):
                                # Pydantic model (VariableConfig)
                                bot_token = var_config.value or ""
                            else:
                                bot_token = str(var_config)
                        
                        if not bot_token:
                            logger.warning(f"[{agent.agent_id}:{trigger_id}] No bot_token found, config={trigger.config}")
                            continue
                        
                        logger.info(f"[{agent.agent_id}:{trigger_id}] Found telegram trigger with token ...{bot_token[-8:]}")
                        triggers.append({
                            "agent_id": agent.agent_id,
                            "trigger_id": trigger_id,
                            "bot_token": bot_token,
                            "subdomain": subdomain,
                        })
            except Exception as e:
                logger.error(f"Error scanning triggers for {subdomain}: {e}")
        
        clear_context()
        return triggers
    
    async def _get_all_subdomains(self, container) -> List[str]:
        """Получает все уникальные subdomains из таблицы agents."""
        try:
            # Читаем все ключи из таблицы agents
            all_data = await container.agent_repository._storage._get_all_by_prefix_and_table(
                "company:", "agents", 1000
            )
            
            subdomains = set()
            for key in all_data.keys():
                # Формат: company:{subdomain}:agent:{agent_id}
                if key.startswith("company:"):
                    parts = key.split(":")
                    if len(parts) >= 2:
                        subdomains.add(parts[1])
            
            if not subdomains:
                # Fallback для dev
                subdomains.add("sss")
            
            logger.debug(f"Found subdomains: {subdomains}")
            return list(subdomains)
        except Exception as e:
            logger.error(f"Error getting subdomains: {e}")
            return ["sss"]
    
    async def _handle_update(
        self,
        agent_id: str,
        trigger_id: str,
        payload: Dict[str, Any],
        subdomain: str,
    ):
        """Обрабатывает update через TelegramTriggerHandler."""
        from apps.agents.src.triggers.handlers.telegram import TelegramTriggerHandler
        from apps.agents.src.container import get_container
        from core.context import set_context, clear_context, Context
        from core.models.identity_models import Company, User
        
        # Устанавливаем контекст для handler
        company = Company(company_id=f"dev-{subdomain}", subdomain=subdomain, name=subdomain)
        dev_user = User(user_id="system", email="system@dev.local", name="System")
        context = Context(
            user=dev_user,
            active_company=company,
            user_companies=[company],
            channel="system",
        )
        set_context(context)
        
        try:
            settings = get_settings()
            base_url = settings.server.get_service_url("agents")
            
            handler = TelegramTriggerHandler(base_url)
            
            await handler.handle(agent_id, trigger_id, payload)
        finally:
            clear_context()
    
    async def _sync_bots(self):
        """Синхронизирует polling боты с текущими триггерами."""
        triggers = await self._get_telegram_triggers()
        
        current_keys: Set[str] = set()
        
        for trigger_data in triggers:
            key = f"{trigger_data['agent_id']}:{trigger_data['trigger_id']}"
            current_keys.add(key)
            
            if key not in self.bots:
                bot = TelegramPollingBot(
                    agent_id=trigger_data["agent_id"],
                    trigger_id=trigger_data["trigger_id"],
                    bot_token=trigger_data["bot_token"],
                    subdomain=trigger_data["subdomain"],
                    handler_callback=self._handle_update,
                )
                self.bots[key] = bot
                asyncio.create_task(bot.run())
                logger.info(f"Started polling bot: {key}")
        
        # Останавливаем удалённые
        for key in list(self.bots.keys()):
            if key not in current_keys:
                self.bots[key].stop()
                del self.bots[key]
                logger.info(f"Stopped polling bot: {key}")
    
    async def run(self):
        """Основной цикл сканирования."""
        self.running = True
        
        logger.info("=" * 50)
        logger.info("Telegram Dev Polling started")
        logger.info("=" * 50)
        
        while self.running:
            await self._sync_bots()
            await asyncio.sleep(self._scan_interval)
        
        # Останавливаем все боты
        for bot in self.bots.values():
            bot.stop()
        
        logger.info("Telegram Dev Polling stopped")
    
    def start(self) -> asyncio.Task:
        """Запускает polling в background."""
        self._task = asyncio.create_task(self.run())
        return self._task
    
    def stop(self):
        """Останавливает polling."""
        self.running = False
        for bot in self.bots.values():
            bot.stop()
        if self._task:
            self._task.cancel()


# Глобальный инстанс
_dev_polling: Optional[TelegramDevPolling] = None


def get_dev_polling() -> TelegramDevPolling:
    global _dev_polling
    if _dev_polling is None:
        _dev_polling = TelegramDevPolling()
    return _dev_polling


async def start_dev_polling():
    """Запускает dev polling если в dev окружении."""
    settings = get_settings()
    
    if settings.server.env != "development":
        logger.info("Not in development mode, skipping Telegram dev polling")
        return
    
    polling = get_dev_polling()
    polling.start()
    logger.info("Telegram dev polling task started")


async def stop_dev_polling():
    """Останавливает dev polling."""
    global _dev_polling
    if _dev_polling:
        _dev_polling.stop()
        _dev_polling = None

"""
AgentDiscoveryService - сервис для управления внешними агентами.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from core.clients import A2AClient
from apps.agents.config import ExternalAgentConfig
from apps.agents.src.db.agent_repository import AgentRepository
from core.logging import get_logger
from apps.agents.src.models import AgentConfig, AgentType, ExternalAgentStatus

logger = get_logger(__name__)


class AgentDiscoveryService:
    """
    Сервис для обнаружения и управления внешними агентами.

    Функции:
    - Инициализация агентов из конфига
    - Динамическая регистрация/удаление агентов
    - Проверка здоровья агентов
    - Получение информации об агентах
    """

    def __init__(
        self,
        repository: AgentRepository,
        a2a_client: A2AClient,
    ):
        self._repository = repository
        self._a2a_client = a2a_client

    async def init_from_config(self, agents_config: List[ExternalAgentConfig]) -> int:
        """
        Инициализирует агентов из конфигурации.

        Args:
            agents_config: Список конфигураций агентов

        Returns:
            Количество успешно зарегистрированных агентов
        """
        registered = 0

        for config in agents_config:
            try:
                agent = await self.register_agent(
                    url=config.url,
                    auth_headers=config.auth_headers,
                    name=config.name,
                )
                if agent:
                    registered += 1
                    logger.info(f"Agent '{agent.name}' registered from config: {config.url}")
            except Exception as e:
                logger.warning(f"Failed to register agent from config {config.url}: {e}")

        logger.info(f"Initialized {registered}/{len(agents_config)} agents from config")
        return registered

    async def register_agent(
        self,
        url: str,
        auth_headers: Optional[Dict[str, str]] = None,
        name: Optional[str] = None,
    ) -> AgentConfig:
        """
        Регистрирует внешнего агента.

        Args:
            url: Base URL агента
            auth_headers: Заголовки авторизации
            name: Название агента (опционально)

        Returns:
            Зарегистрированный агент

        Raises:
            ValueError: Если агент недоступен или уже зарегистрирован
        """
        url = url.rstrip("/")

        # Проверяем существующих агентов с таким URL
        all_agents = await self._repository.list_all(limit=10000)
        for existing in all_agents:
            if existing.type == AgentType.EXTERNAL and existing.url == url:
                logger.info(f"Agent already registered: {url}")
                return existing

        agent_card = await self._fetch_agent_card(url, auth_headers)

        agent_id = self._generate_agent_id(url)
        agent_name = name or agent_card.get("name", agent_id)

        now = datetime.now(timezone.utc)

        agent = AgentConfig(
            agent_id=agent_id,
            type=AgentType.EXTERNAL,
            url=url,
            name=agent_name,
            description=agent_card.get("description", ""),
            auth_headers=auth_headers or {},
            status=ExternalAgentStatus.ACTIVE,
            last_health_check=now,
            agent_card=agent_card,
            created_at=now,
            updated_at=now,
        )

        await self._repository.set(agent)
        logger.info(f"Registered agent: {agent_name} ({url})")

        return agent

    async def unregister_agent(self, agent_id: str) -> bool:
        """
        Удаляет агента из реестра.

        Args:
            agent_id: ID агента

        Returns:
            True если удален
        """
        result = await self._repository.delete(agent_id)
        if result:
            logger.info(f"Unregistered agent: {agent_id}")
        return result

    async def get_agent(self, agent_id: str) -> Optional[AgentConfig]:
        """
        Получает агента по ID.

        Args:
            agent_id: ID агента

        Returns:
            AgentConfig или None
        """
        agent = await self._repository.get(agent_id)
        # Проверяем что это external агент
        if agent and agent.type == AgentType.EXTERNAL:
            return agent
        return None

    async def get_agent_by_url(self, url: str) -> Optional[AgentConfig]:
        """
        Получает агента по URL.

        Args:
            url: URL агента

        Returns:
            AgentConfig или None
        """
        url = url.rstrip("/")
        all_agents = await self._repository.list_all(limit=10000)
        for agent in all_agents:
            if agent.type == AgentType.EXTERNAL and agent.url == url:
                return agent
        return None

    async def list_agents(self, only_active: bool = True) -> List[AgentConfig]:
        """
        Возвращает список агентов.

        Args:
            only_active: Только активные агенты

        Returns:
            Список агентов
        """
        all_agents = await self._repository.list_all(limit=10000)
        external_agents = [a for a in all_agents if a.type == AgentType.EXTERNAL]
        
        if only_active:
            return [a for a in external_agents if a.status == ExternalAgentStatus.ACTIVE]
        return external_agents

    async def health_check_all(self) -> Dict[str, bool]:
        """
        Проверяет здоровье всех агентов.

        Returns:
            Словарь {agent_id: is_healthy}
        """
        agents = await self._repository.list_all()
        results = {}

        for agent in agents:
            is_healthy = await self.health_check_agent(agent.agent_id)
            results[agent.agent_id] = is_healthy

        return results

    async def health_check_agent(self, agent_id: str) -> bool:
        """
        Проверяет здоровье конкретного агента.

        Args:
            agent_id: ID агента

        Returns:
            True если агент здоров
        """
        agent = await self._repository.get(agent_id)
        if agent is None or agent.type != AgentType.EXTERNAL:
            return False

        try:
            agent_card = await self._fetch_agent_card(agent.url, agent.auth_headers)

            # Обновляем агента с новым статусом
            agent.status = ExternalAgentStatus.ACTIVE
            agent.last_health_check = datetime.now(timezone.utc)
            agent.agent_card = agent_card
            agent.updated_at = datetime.now(timezone.utc)
            await self._repository.set(agent)

            logger.debug(f"Agent {agent_id} is healthy")
            return True

        except Exception as e:
            logger.warning(f"Agent {agent_id} health check failed: {e}")

            # Обновляем агента с unhealthy статусом
            agent.status = ExternalAgentStatus.UNHEALTHY
            agent.last_health_check = datetime.now(timezone.utc)
            agent.updated_at = datetime.now(timezone.utc)
            await self._repository.set(agent)

            return False

    async def _fetch_agent_card(
        self,
        url: str,
        auth_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Получает agent-card от агента.

        Args:
            url: URL агента
            auth_headers: Заголовки авторизации

        Returns:
            AgentCard как dict
        """
        return await self._a2a_client.get_agent_card(url, auth_headers)

    def _generate_agent_id(self, url: str) -> str:
        """
        Генерирует ID агента из URL.

        Args:
            url: URL агента

        Returns:
            agent_id
        """
        parsed = urlparse(url)
        host = parsed.hostname or "unknown"
        port = parsed.port or 80

        return f"{host}_{port}".replace(".", "_").replace("-", "_")

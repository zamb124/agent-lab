"""
FlowDiscoveryService — регистрация и health-check внешних flows (EXTERNAL / A2A).
"""

from datetime import datetime, timezone
from urllib.parse import urlparse

from apps.flows.config import ExternalFlowConfig
from apps.flows.src.db.flow_repository import FlowRepository
from apps.flows.src.models import ExternalAgentStatus, FlowConfig, FlowType
from core.clients.a2a_client import A2AClient
from core.logging import get_logger
from core.types import JsonObject

logger = get_logger(__name__)


class FlowDiscoveryService:
    """
    Обнаружение и учёт внешних flows (type=EXTERNAL): регистрация по URL, health-check.
    """

    def __init__(
        self,
        repository: FlowRepository,
        a2a_client: A2AClient,
    ) -> None:
        self._repository: FlowRepository = repository
        self._a2a_client: A2AClient = a2a_client

    async def init_from_config(self, external_flows_config: list[ExternalFlowConfig]) -> int:
        """Регистрирует flows из конфигурации приложения."""
        registered = 0

        for item in external_flows_config:
            try:
                flow_cfg = await self.register_agent(
                    url=item.url,
                    headers=item.headers,
                    name=item.name,
                )
                registered += 1
                logger.info(f"Flow '{flow_cfg.name}' registered from config: {item.url}")
            except Exception as e:
                logger.warning(f"Failed to register external flow from config {item.url}: {e}")

        logger.info(f"Initialized {registered}/{len(external_flows_config)} external flows from config")
        return registered

    async def register_agent(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        name: str | None = None,
    ) -> FlowConfig:
        """
        Регистрирует внешний flow по A2A base URL.

        Исключения:
            ValueError: endpoint недоступен или дубликат URL
        """
        url = url.rstrip("/")

        stored_flows = await self._repository.list(limit=10000)
        for existing in stored_flows:
            if existing.type == FlowType.EXTERNAL and existing.url == url:
                logger.info(f"External flow already registered: {url}")
                return existing

        card_payload = await self._fetch_agent_card(url, headers)

        flow_id = self._generate_flow_id(url)
        if name is not None and name.strip():
            display_name = name
        else:
            card_name = card_payload.get("name")
            if not isinstance(card_name, str) or not card_name.strip():
                raise ValueError("A2A agent-card.name is required")
            display_name = card_name

        card_description = card_payload.get("description")
        if not isinstance(card_description, str):
            raise ValueError("A2A agent-card.description is required")

        now = datetime.now(timezone.utc)

        flow_cfg = FlowConfig(
            flow_id=flow_id,
            type=FlowType.EXTERNAL,
            url=url,
            name=display_name,
            description=card_description,
            headers=headers or {},
            status=ExternalAgentStatus.ACTIVE,
            last_health_check=now,
            agent_card=card_payload,
            created_at=now,
            updated_at=now,
        )

        _ = await self._repository.set(flow_cfg)
        logger.info(f"Registered external flow: {display_name} ({url})")

        return flow_cfg

    async def unregister_agent(self, flow_id: str) -> bool:
        """Удаляет запись EXTERNAL flow из репозитория."""
        result = await self._repository.delete(flow_id)
        if result:
            logger.info(f"Unregistered external flow: {flow_id}")
        return result

    async def get_flow(self, flow_id: str) -> FlowConfig | None:
        """Внешний flow (EXTERNAL) по flow_id."""
        flow_cfg = await self._repository.get(flow_id)
        if flow_cfg and flow_cfg.type == FlowType.EXTERNAL:
            return flow_cfg
        return None

    async def get_flow_by_url(self, url: str) -> FlowConfig | None:
        """Внешний flow по нормализованному base URL."""
        url = url.rstrip("/")
        stored_flows = await self._repository.list(limit=10000)
        for row in stored_flows:
            if row.type == FlowType.EXTERNAL and row.url == url:
                return row
        return None

    async def list_agents(self, only_active: bool = True) -> list[FlowConfig]:
        """Список EXTERNAL flows (имя метода историческое; сущность — flow)."""
        stored_flows = await self._repository.list(limit=10000)
        external = [row for row in stored_flows if row.type == FlowType.EXTERNAL]

        if only_active:
            return [row for row in external if row.status == ExternalAgentStatus.ACTIVE]
        return external

    async def health_check_all(self) -> dict[str, bool]:
        """Health-check по всем записям в репозитории."""
        rows = await self._repository.list(limit=10000)
        results: dict[str, bool] = {}

        for row in rows:
            is_healthy = await self.health_check_agent(row.flow_id)
            results[row.flow_id] = is_healthy

        return results

    async def health_check_agent(self, flow_id: str) -> bool:
        """Health-check для EXTERNAL flow по flow_id."""
        ext_cfg = await self._repository.get(flow_id)
        if ext_cfg is None or ext_cfg.type != FlowType.EXTERNAL:
            return False
        if ext_cfg.url is None:
            return False

        try:
            card_payload = await self._fetch_agent_card(ext_cfg.url, ext_cfg.headers)

            ext_cfg.status = ExternalAgentStatus.ACTIVE
            ext_cfg.last_health_check = datetime.now(timezone.utc)
            ext_cfg.agent_card = card_payload
            ext_cfg.updated_at = datetime.now(timezone.utc)
            _ = await self._repository.set(ext_cfg)

            logger.debug(f"External flow {flow_id} is healthy")
            return True

        except Exception as e:
            logger.warning(f"External flow {flow_id} health check failed: {e}")

            ext_cfg.status = ExternalAgentStatus.UNHEALTHY
            ext_cfg.last_health_check = datetime.now(timezone.utc)
            ext_cfg.updated_at = datetime.now(timezone.utc)
            _ = await self._repository.set(ext_cfg)

            return False

    async def _fetch_agent_card(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> JsonObject:
        """HTTP: A2A agent-card (спека A2A)."""
        return await self._a2a_client.get_agent_card(url, headers)

    def _generate_flow_id(self, url: str) -> str:
        """Стабильный flow_id из host:port URL."""
        parsed = urlparse(url)
        if parsed.hostname is None:
            raise ValueError("External flow URL must include host")
        host = parsed.hostname
        if parsed.port is not None:
            port = parsed.port
        elif parsed.scheme == "https":
            port = 443
        elif parsed.scheme == "http":
            port = 80
        else:
            raise ValueError("External flow URL scheme must be http or https")

        return f"{host}_{port}".replace(".", "_").replace("-", "_")

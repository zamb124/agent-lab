"""
Модели для работы с MCP (Model Context Protocol) серверами.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import ConfigDict
from datetime import datetime

from apps.agents.models.core_models import BuilderEntity
from core.fields import Field
from core.context import get_context


class MCPTransportType(str, Enum):
    """Типы транспорта для MCP"""
    
    HTTP = "http"  # Обычные HTTP POST запросы
    SSE = "sse"    # Server-Sent Events (streaming)


class MCPServerConfig(BuilderEntity):
    """Конфигурация MCP сервера для компании"""
    
    model_config = ConfigDict(
        json_schema_extra={"storage_prefix": "mcp_server"}
    )
    
    server_id: str = Field(
        frozen=True,
        title="ID сервера",
        description="Уникальный идентификатор MCP сервера"
    )
    company_id: str = Field(
        frozen=True,
        title="ID компании",
        description="Компания владелец сервера",
        readonly=True
    )
    name: str = Field(
        title="Название",
        description="Название MCP сервера",
        placeholder="Context7 MCP"
    )
    description: Optional[str] = Field(
        default=None,
        title="Описание",
        description="Описание функциональности сервера"
    )
    
    # Тип транспорта
    transport_type: MCPTransportType = Field(
        default=MCPTransportType.HTTP,
        title="Тип транспорта",
        description="HTTP или SSE"
    )
    
    # Настройки подключения
    url: str = Field(
        title="URL",
        description="URL MCP сервера",
        placeholder="https://mcp.context7.com/mcp"
    )
    headers: Dict[str, str] = Field(
        default_factory=dict,
        title="HTTP заголовки",
        description="Заголовки для авторизации (поддержка @var: для секретов)",
        widget_attrs={"rows": 4, "placeholder": '{"Authorization": "@var:mcp_api_key"}'}
    )
    timeout: int = Field(
        default=30,
        title="Таймаут (сек)",
        description="Таймаут HTTP запросов",
        ge=5,
        le=300
    )
    use_proxy: bool = Field(
        default=True,
        title="Использовать прокси",
        description="Использовать глобальный прокси для запросов к серверу"
    )
    
    # Метаданные
    is_active: bool = Field(
        default=True,
        title="Активен",
        description="Активен ли сервер"
    )
    auto_sync_tools: bool = Field(
        default=True,
        title="Автосинхронизация",
        description="Автоматически синхронизировать список тулов при старте"
    )
    
    # Кэш
    cached_tools: List[str] = Field(
        default_factory=list,
        title="Кэшированные тулы",
        description="Список синхронизированных tool_id",
        exclude_from_form=True
    )
    last_sync_at: Optional[datetime] = Field(
        default=None,
        title="Последняя синхронизация",
        description="Время последней синхронизации тулов",
        exclude_from_form=True
    )
    
    def __init__(self, **data):
        """Автоматически подставляет company_id из контекста"""
        if 'company_id' not in data:
            context = get_context()
            if context and context.active_company:
                data['company_id'] = context.active_company.company_id
        super().__init__(**data)


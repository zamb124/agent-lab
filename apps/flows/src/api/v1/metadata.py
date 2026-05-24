"""API endpoints для метаданных платформы."""

from fastapi import APIRouter

from apps.flows.config import get_settings
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models.exception_absorb_allow import list_exception_absorb_allow_values
from core.types import JsonObject

router = APIRouter(tags=["metadata"])


# Категория -> упорядоченный человекочитаемый ключ для UI-сайдбара.
# Сами типы нод и связи с runtime — в `apps/flows/src/runtime/nodes.py`
# (NodeType enum в `apps/flows/src/models/enums.py`).
_NODE_TYPES: list[JsonObject] = [
    {
        "category": "core",
        "type": "llm_node",
        "name": "LLM Node",
        "icon": "llm_node",
        "description": "LLM и tools (ReAct)",
        "color": "#f59e0b",
        "inputs": 1,
        "outputs": 1,
    },
    {
        "category": "core",
        "type": "code",
        "name": "Code Node",
        "icon": "code",
        "description": "Python/JavaScript/TypeScript/Go через isolated runners",
        "color": "#8b5cf6",
        "inputs": 1,
        "outputs": 1,
    },
    {
        "category": "tools",
        "type": "external_api",
        "name": "External API",
        "icon": "globe",
        "description": "HTTP API вызов",
        "color": "#06b6d4",
        "inputs": 1,
        "outputs": 1,
    },
    {
        "category": "tools",
        "type": "mcp",
        "name": "MCP Tool",
        "icon": "plug",
        "description": "MCP сервер tool",
        "color": "#8b5cf6",
        "inputs": 1,
        "outputs": 1,
    },
    {
        "category": "integrations",
        "type": "remote_flow",
        "name": "Remote A2A",
        "icon": "cloud",
        "description": "Внешний endpoint по A2A",
        "color": "#3b82f6",
        "inputs": 1,
        "outputs": 1,
    },
    {
        "category": "integrations",
        "type": "flow",
        "name": "Flow Node",
        "icon": "workflow",
        "description": "Вложенный flow (subflow)",
        "color": "#ec4899",
        "inputs": 1,
        "outputs": 1,
    },
    {
        "category": "integrations",
        "type": "resource",
        "name": "Resource Node",
        "icon": "box",
        "description": "Ресурс на графе (pass-through)",
        "color": "#a78bfa",
        "inputs": 1,
        "outputs": 1,
    },
    {
        "category": "channels",
        "type": "channel",
        "name": "Channel",
        "icon": "send",
        "description": "Отправка в каналы (Telegram, Email)",
        "color": "#99A6F9",
        "inputs": 1,
        "outputs": 1,
    },
    {
        "category": "channels",
        "type": "hitl_node",
        "name": "Оператор",
        "icon": "users",
        "description": "Пауза до специалиста очереди",
        "color": "#0ea5e9",
        "inputs": 1,
        "outputs": 1,
    },
]


# Resource-типы для отдельного раздела «Ресурсы» в редакторе. Runtime resources
# остаются декларативными LLM-конфигами; sandbox code использует capabilities/tools.
_RESOURCE_TYPES: list[JsonObject] = [
    {"type": "llm",    "name": "LLM",    "icon": "bot",      "description": "LLM модель",                "color": "#ec4899"},
]


@router.get("/node-types")
async def get_node_types(container: ContainerDep) -> list[JsonObject]:
    """Список доступных runtime-типов нод для палитры редактора."""
    _ = container
    return _NODE_TYPES


@router.get("/resource-types")
async def get_resource_types(container: ContainerDep) -> list[JsonObject]:
    """Список типов runtime resources."""
    _ = container
    return _RESOURCE_TYPES


@router.get("/exception-absorb-allow-names")
async def get_exception_absorb_allow_names(container: ContainerDep) -> list[str]:
    """Имена классов исключений для whitelist exception_allow_types в редакторе нод."""
    _ = container
    return list_exception_absorb_allow_values()


@router.get("/execution-limits")
async def get_execution_limits(container: ContainerDep) -> dict[str, int]:
    """Лимиты исполнения графа для UI (кламп max_visits_per_run и т.п.)."""
    _ = container
    return {"graph_max_iterations": get_settings().graph_max_iterations}

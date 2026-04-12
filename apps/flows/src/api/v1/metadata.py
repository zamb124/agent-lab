"""
API endpoints для метаданных платформы.
Предоставляет информацию о типах нод, доступных моделях и т.д.
"""

from typing import Any, Dict, List

from fastapi import APIRouter

from apps.flows.src.dependencies import ContainerDep

router = APIRouter(tags=["metadata"])


@router.get("/node-types")
async def get_node_types(container: ContainerDep) -> List[Dict[str, Any]]:
    """
    Возвращает список доступных типов нод для визуального редактора.
    Используется в редакторе графа (canvas) для панели типов нод.
    """
    _ = container
    return [
        {
            "type": "llm_node",
            "name": "React Node",
            "icon": "brain",
            "description": "LLM нода с ReAct циклом",
            "color": "#6366f1",
            "inputs": 1,
            "outputs": 1,
        },
        {
            "type": "code",
            "name": "Code",
            "icon": "code",
            "description": "Выполнение кода (Python, JS, Go)",
            "color": "#f59e0b",
            "inputs": 1,
            "outputs": 1,
        },
        {
            "type": "flow",
            "name": "Flow Node",
            "icon": "git-branch",
            "description": "Вложенный flow (subflow)",
            "color": "#10b981",
            "inputs": 1,
            "outputs": 1,
        },
        {
            "type": "remote_flow",
            "name": "Remote flow",
            "icon": "cloud",
            "description": "Внешний агент по A2A",
            "color": "#3b82f6",
            "inputs": 1,
            "outputs": 1,
        },
        {
            "type": "external_api",
            "name": "ApiNode",
            "icon": "globe",
            "description": "HTTP API вызов",
            "color": "#ec4899",
            "inputs": 1,
            "outputs": 1,
        },
        {
            "type": "mcp",
            "name": "MCP",
            "icon": "plug",
            "description": "MCP tool",
            "color": "#8b5cf6",
            "inputs": 1,
            "outputs": 1,
        },
    ]


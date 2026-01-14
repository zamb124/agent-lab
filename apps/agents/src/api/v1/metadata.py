"""
API endpoints для метаданных платформы.
Предоставляет информацию о типах нод, доступных моделях и т.д.
"""

from typing import Any, Dict, List

from fastapi import APIRouter

router = APIRouter(tags=["metadata"])


@router.get("/node-types")
async def get_node_types() -> List[Dict[str, Any]]:
    """
    Возвращает список доступных типов нод для визуального редактора.
    Используется в AgentCanvas для отображения toolbar.
    """
    return [
        {
            "type": "react_node",
            "name": "React Node",
            "icon": "brain",
            "description": "LLM нода с ReAct циклом",
            "color": "#6366f1",
            "inputs": 1,
            "outputs": 1,
        },
        {
            "type": "function",
            "name": "Function",
            "icon": "code",
            "description": "Python функция",
            "color": "#f59e0b",
            "inputs": 1,
            "outputs": 1,
        },
        {
            "type": "agent",
            "name": "Agent Node",
            "icon": "git-branch",
            "description": "Вложенный agent",
            "color": "#10b981",
            "inputs": 1,
            "outputs": 1,
        },
        {
            "type": "remote_agent",
            "name": "Remote Agent",
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
            "type": "tool",
            "name": "Tool",
            "icon": "tool",
            "description": "Tool (инструмент)",
            "color": "#8b5cf6",
            "inputs": 1,
            "outputs": 1,
        },
    ]


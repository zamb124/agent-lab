"""
Поля ExecutionState - общие для всех языков.
"""

from typing import Any, Dict, List

STATE_FIELDS: List[Dict[str, Any]] = [
    {
        "name": "content",
        "type": "str",
        "description": "Текст последнего сообщения пользователя",
        "readonly": False,
    },
    {
        "name": "response",
        "type": "str",
        "description": "Ответ для пользователя (установите)",
        "readonly": False,
    },
    {
        "name": "messages",
        "type": "List[Message]",
        "description": "История сообщений",
        "readonly": False,
    },
    {
        "name": "files",
        "type": "List[dict]",
        "description": "Файлы [{name, path, mime_type, size}]",
        "readonly": True,
    },
    {
        "name": "user_id",
        "type": "str",
        "description": "ID пользователя",
        "readonly": True,
    },
    {
        "name": "user_groups",
        "type": "List[str]",
        "description": "Группы пользователя",
        "readonly": True,
    },
    {
        "name": "variables",
        "type": "dict",
        "description": "Переменные агента",
        "readonly": True,
    },
    {
        "name": "current_nodes",
        "type": "List[str]",
        "description": "Текущие ноды для выполнения",
        "readonly": True,
    },
    {
        "name": "task_id",
        "type": "str",
        "description": "ID задачи",
        "readonly": True,
    },
    {
        "name": "context_id",
        "type": "str",
        "description": "ID контекста",
        "readonly": True,
    },
    {
        "name": "session_id",
        "type": "str",
        "description": "ID сессии",
        "readonly": True,
    },
    {
        "name": "tool_results",
        "type": "dict",
        "description": "Результаты выполненных tools",
        "readonly": True,
    },
]

"""
Поля ExecutionState - общие для всех языков.
"""

from typing import Any, Dict, List

STATE_FIELDS: List[Dict[str, Any]] = [
    {
        "name": "content",
        "type": "str",
        "description": "Текст последнего сообщения пользователя (`state['content']`).",
        "readonly": False,
    },
    {
        "name": "response",
        "type": "str",
        "description": "Ответ для пользователя; задайте перед завершением ноды.",
        "readonly": False,
    },
    {
        "name": "messages",
        "type": "List[Message]",
        "description": "История диалога (A2A `Message`).",
        "readonly": False,
    },
    {
        "name": "files",
        "type": "List[dict]",
        "description": "Вложения: элементы с ключами `name`, `path`, `mime_type`, `size` и др.",
        "readonly": True,
    },
    {
        "name": "user_id",
        "type": "str",
        "description": "Идентификатор пользователя (`user_id`).",
        "readonly": True,
    },
    {
        "name": "user_groups",
        "type": "List[str]",
        "description": "Группы пользователя в компании.",
        "readonly": True,
    },
    {
        "name": "variables",
        "type": "dict",
        "description": "Переменные flow (только чтение в inline-коде через одноимённый глобал `variables`).",
        "readonly": True,
    },
    {
        "name": "current_nodes",
        "type": "List[str]",
        "description": "Идентификаторы нод, активных в текущем шаге графа.",
        "readonly": True,
    },
    {
        "name": "task_id",
        "type": "str",
        "description": "Идентификатор задачи выполнения.",
        "readonly": True,
    },
    {
        "name": "context_id",
        "type": "str",
        "description": "Идентификатор контекста A2A / сессии выполнения.",
        "readonly": True,
    },
    {
        "name": "session_id",
        "type": "str",
        "description": "Идентификатор сессии пользователя.",
        "readonly": True,
    },
    {
        "name": "tool_results",
        "type": "dict",
        "description": "Результаты вызванных tools по имени tool.",
        "readonly": True,
    },
]

"""
Repositories - паттерн Repository для работы с моделями через Storage.

Включает:
- Storage: низкоуровневый key-value доступ к БД
- BaseRepository: базовый класс для репозиториев
- AgentRepository: работа с агентами
- FlowRepository: работа с flows
- TaskRepository: работа с задачами
- SessionRepository: работа с сессиями
- ToolRepository: работа с инструментами

Репозитории инкапсулируют бизнес-логику работы с данными,
в то время как Storage остается простым key-value хранилищем.
"""

from app.db.repositories.storage import Storage
from app.db.repositories.base import BaseRepository
from app.db.repositories.agent_repository import AgentRepository
from app.db.repositories.flow_repository import FlowRepository
from app.db.repositories.task_repository import TaskRepository
from app.db.repositories.session_repository import SessionRepository
from app.db.repositories.tool_repository import ToolRepository

__all__ = [
    "Storage",
    "BaseRepository",
    "AgentRepository",
    "FlowRepository",
    "TaskRepository",
    "SessionRepository",
    "ToolRepository",
]


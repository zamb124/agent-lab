"""
Pydantic модели для задач CRM.
"""

from datetime import datetime, date
from typing import Optional, Dict, Any, List
from enum import Enum

from pydantic import BaseModel, ConfigDict

from core.fields import Field


class TaskPriority(str, Enum):
    """Приоритеты задач"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TaskStatus(str, Enum):
    """Статусы задач"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskCreate(BaseModel):
    """Создание задачи"""
    
    model_config = ConfigDict(from_attributes=True)
    
    title: str = Field(
        title="Заголовок"
    )
    description: Optional[str] = Field(
        default=None,
        title="Описание"
    )
    priority: TaskPriority = Field(
        default=TaskPriority.MEDIUM,
        title="Приоритет"
    )
    due_date: Optional[date] = Field(
        default=None,
        title="Дедлайн"
    )
    linked_entity_id: Optional[str] = Field(
        default=None,
        title="Связанная сущность"
    )
    source_note_id: Optional[str] = Field(
        default=None,
        title="Исходная заметка"
    )
    tags: List[str] = Field(
        default_factory=list,
        title="Теги"
    )
    assignees: List[str] = Field(
        default_factory=list,
        title="Соучастники"
    )


class TaskUpdate(BaseModel):
    """Обновление задачи"""
    
    model_config = ConfigDict(from_attributes=True)
    
    title: Optional[str] = Field(default=None, title="Заголовок")
    description: Optional[str] = Field(default=None, title="Описание")
    priority: Optional[TaskPriority] = Field(default=None, title="Приоритет")
    status: Optional[TaskStatus] = Field(default=None, title="Статус")
    due_date: Optional[date] = Field(default=None, title="Дедлайн")
    linked_entity_id: Optional[str] = Field(default=None, title="Связанная сущность")
    tags: Optional[List[str]] = Field(default=None, title="Теги")
    assignees: Optional[List[str]] = Field(default=None, title="Соучастники")


class TaskResponse(BaseModel):
    """Ответ с задачей"""
    
    model_config = ConfigDict(from_attributes=True)
    
    task_id: str = Field(title="ID задачи", readonly=True)
    company_id: str = Field(title="ID компании", readonly=True)
    user_id: str = Field(title="ID пользователя", readonly=True)
    title: str = Field(title="Заголовок")
    description: Optional[str] = Field(default=None, title="Описание")
    priority: str = Field(title="Приоритет")
    status: str = Field(title="Статус")
    due_date: Optional[date] = Field(default=None, title="Дедлайн")
    linked_entity_id: Optional[str] = Field(default=None, title="Связанная сущность")
    source_note_id: Optional[str] = Field(default=None, title="Исходная заметка")
    tags: List[str] = Field(default_factory=list, title="Теги")
    assignees: List[str] = Field(default_factory=list, title="Соучастники")
    created_at: datetime = Field(title="Дата создания", readonly=True)
    updated_at: datetime = Field(title="Дата обновления", readonly=True)
    
    # Опционально: информация о связанной сущности
    linked_entity: Optional[Dict[str, Any]] = Field(
        default=None,
        title="Связанная сущность (развернуто)"
    )


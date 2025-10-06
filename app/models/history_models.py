"""
Модели для работы с историей сообщений и сессий
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum
from pydantic import BaseModel
from app.fields import Field


class MessageRole(str, Enum):
    """Роли сообщений"""
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    SYSTEM = "system"


class ToolCallInfo(BaseModel):
    """Информация о вызове инструмента"""
    
    tool_name: str = Field(
        title="Название инструмента",
        description="Имя вызванного инструмента"
    )
    tool_id: str = Field(
        title="ID вызова",
        description="Уникальный идентификатор вызова инструмента"
    )
    arguments: Dict[str, Any] = Field(
        default_factory=dict,
        title="Аргументы",
        description="Аргументы переданные в инструмент"
    )
    result: Optional[str] = Field(
        default=None,
        title="Результат",
        description="Результат выполнения инструмента"
    )


class MessageItem(BaseModel):
    """Одно сообщение из истории"""
    
    role: MessageRole = Field(
        title="Роль",
        description="Роль отправителя сообщения"
    )
    content: str = Field(
        title="Содержимое",
        description="Текст сообщения"
    )
    timestamp: Optional[datetime] = Field(
        default=None,
        title="Время",
        description="Время отправки сообщения"
    )
    tool_calls: List[ToolCallInfo] = Field(
        default_factory=list,
        title="Вызовы инструментов",
        description="Список вызовов инструментов в этом сообщении"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        title="Метаданные",
        description="Дополнительные метаданные сообщения"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "role": "user",
                "content": "Какая погода в Москве?",
                "timestamp": "2025-10-06T10:00:00Z",
                "tool_calls": [],
                "metadata": {}
            }
        }


class CheckpointInfo(BaseModel):
    """Информация о checkpoint из LangGraph"""
    
    checkpoint_id: str = Field(
        title="ID checkpoint",
        description="Уникальный идентификатор checkpoint"
    )
    thread_id: str = Field(
        title="Thread ID",
        description="ID треда (session_id)"
    )
    checkpoint_ns: str = Field(
        default="",
        title="Namespace",
        description="Namespace checkpoint"
    )
    step: int = Field(
        default=0,
        title="Шаг",
        description="Номер шага в графе"
    )
    timestamp: Optional[datetime] = Field(
        default=None,
        title="Время",
        description="Время создания checkpoint"
    )
    messages: List[MessageItem] = Field(
        default_factory=list,
        title="Сообщения",
        description="Сообщения в этом checkpoint"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        title="Метаданные",
        description="Метаданные checkpoint"
    )


class MessageHistoryResponse(BaseModel):
    """Ответ с историей сообщений"""
    
    session_id: str = Field(
        title="ID сессии",
        description="Идентификатор сессии"
    )
    thread_id: str = Field(
        title="Thread ID",
        description="ID треда для LangGraph"
    )
    flow_id: Optional[str] = Field(
        default=None,
        title="Flow ID",
        description="Идентификатор потока"
    )
    flow_name: Optional[str] = Field(
        default=None,
        title="Название Flow",
        description="Человекочитаемое название потока"
    )
    messages: List[MessageItem] = Field(
        default_factory=list,
        title="Сообщения",
        description="Список всех сообщений в хронологическом порядке"
    )
    checkpoints: List[CheckpointInfo] = Field(
        default_factory=list,
        title="Checkpoints",
        description="Список всех checkpoint'ов (для детального анализа)"
    )
    total_messages: int = Field(
        default=0,
        title="Всего сообщений",
        description="Общее количество сообщений"
    )
    total_checkpoints: int = Field(
        default=0,
        title="Всего checkpoints",
        description="Общее количество checkpoint'ов"
    )
    created_at: Optional[datetime] = Field(
        default=None,
        title="Создано",
        description="Время первого сообщения"
    )
    last_activity: Optional[datetime] = Field(
        default=None,
        title="Последняя активность",
        description="Время последнего сообщения"
    )
    
    class Config:
        storage_prefix = "message_history"


class SessionListItem(BaseModel):
    """Элемент списка сессий для таблицы"""
    
    session_id: str = Field(
        title="ID сессии",
        description="Идентификатор сессии"
    )
    flow_id: str = Field(
        title="Flow",
        description="Идентификатор потока"
    )
    flow_name: Optional[str] = Field(
        default=None,
        title="Название Flow",
        description="Человекочитаемое название потока"
    )
    platform: str = Field(
        title="Платформа",
        description="Платформа (web/telegram/api)"
    )
    user_id: str = Field(
        title="Пользователь",
        description="Идентификатор пользователя"
    )
    user_name: Optional[str] = Field(
        default=None,
        title="Имя пользователя",
        description="Имя пользователя"
    )
    status: str = Field(
        title="Статус",
        description="Статус сессии"
    )
    message_count: int = Field(
        default=0,
        title="Сообщений",
        description="Количество сообщений в сессии"
    )
    created_at: Optional[datetime] = Field(
        default=None,
        title="Создано",
        description="Время создания сессии"
    )
    last_activity: Optional[datetime] = Field(
        default=None,
        title="Последняя активность",
        description="Время последней активности"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        title="Метаданные",
        description="Дополнительные метаданные"
    )


class SessionListResponse(BaseModel):
    """Ответ со списком сессий"""
    
    sessions: List[SessionListItem] = Field(
        default_factory=list,
        title="Сессии",
        description="Список сессий"
    )
    total: int = Field(
        default=0,
        title="Всего",
        description="Общее количество сессий"
    )
    limit: int = Field(
        default=50,
        title="Лимит",
        description="Максимальное количество результатов"
    )
    offset: int = Field(
        default=0,
        title="Смещение",
        description="Смещение для пагинации"
    )
    filters: Dict[str, Any] = Field(
        default_factory=dict,
        title="Фильтры",
        description="Примененные фильтры"
    )
    
    class Config:
        storage_prefix = "session_list"

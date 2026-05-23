"""
Pydantic модели для запросов на доступ.
"""

from datetime import datetime
from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field


class AccessRequestStatus(str, Enum):
    """Статус запроса на доступ"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ResourceType(str, Enum):
    """Тип ресурса для запроса доступа"""

    NOTE = "note"
    ENTITY = "entity"


class AccessRequestCreate(BaseModel):
    """Создание запроса на доступ"""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    resource_type: ResourceType = Field(
        title="Тип ресурса", description="Тип ресурса (note или entity)"
    )
    resource_id: str = Field(title="ID ресурса", description="ID заметки или сущности")
    message: str | None = Field(
        default=None, max_length=1000, title="Сообщение", description="Сообщение владельцу ресурса"
    )
    include_dependencies: bool = Field(
        default=False, title="Включить зависимости", description="Копировать с relationships"
    )
    max_depth: int = Field(
        default=1,
        ge=1,
        le=5,
        title="Глубина копирования",
        description="Максимальная глубина для relationships",
    )


class AccessRequestUpdate(BaseModel):
    """Обновление статуса запроса"""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    status: AccessRequestStatus = Field(title="Новый статус")


class AccessRequestResponse(BaseModel):
    """Ответ с данными запроса на доступ"""

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)

    access_request_id: str = Field(title="ID запроса доступа")
    company_id: str = Field(title="ID компании")
    requester_id: str = Field(title="ID запрашивающего")
    owner_id: str = Field(title="ID владельца")
    resource_type: str = Field(title="Тип ресурса")
    resource_id: str = Field(title="ID ресурса")
    message: str | None = Field(default=None, title="Сообщение")
    status: str = Field(title="Статус")
    created_at: datetime = Field(title="Дата создания")
    updated_at: datetime = Field(title="Дата обновления")

    # Дополнительные поля для UI
    requester_name: str | None = Field(default=None, title="Имя запрашивающего")
    resource_title: str | None = Field(default=None, title="Название ресурса")

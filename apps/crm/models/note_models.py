"""
Pydantic модели для заметок CRM (Daily Notes).
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from enum import Enum

from pydantic import BaseModel, ConfigDict

from core.fields import Field


class NoteType(str, Enum):
    """Типы заметок"""
    FREEFORM = "freeform"
    MEETING_MINUTES = "meeting_minutes"
    CALL_LOG = "call_log"


class NoteStatus(str, Enum):
    """Статусы заметок"""
    DRAFT = "draft"
    PUBLISHED = "published"


class NoteVisibility(str, Enum):
    """Видимость заметок"""
    PUBLIC = "public"
    PRIVATE = "private"
    SHARED = "shared"


class NoteCreate(BaseModel):
    """Создание заметки"""
    
    model_config = ConfigDict(from_attributes=True)
    
    title: str = Field(
        title="Заголовок"
    )
    content: str = Field(
        title="Содержимое",
        description="Markdown текст"
    )
    note_type: NoteType = Field(
        default=NoteType.FREEFORM,
        title="Тип заметки"
    )
    note_date: date = Field(
        title="Дата заметки"
    )
    linked_entity_ids: List[str] = Field(
        default_factory=list,
        title="Связанные сущности"
    )
    is_template: bool = Field(
        default=False,
        title="Шаблон",
        description="Если True - заметка является шаблоном"
    )
    status: NoteStatus = Field(
        default=NoteStatus.PUBLISHED,
        title="Статус"
    )
    visibility: NoteVisibility = Field(
        default=NoteVisibility.PUBLIC,
        title="Видимость"
    )
    shared_with: List[str] = Field(
        default_factory=list,
        title="Поделено с",
        description="Список user_ids с доступом"
    )
    attachment_ids: List[str] = Field(
        default_factory=list,
        title="Прикрепленные файлы",
        description="Список file_ids из core/files"
    )


class NoteUpdate(BaseModel):
    """Обновление заметки"""
    
    model_config = ConfigDict(from_attributes=True)
    
    title: Optional[str] = Field(default=None, title="Заголовок")
    content: Optional[str] = Field(default=None, title="Содержимое")
    note_type: Optional[NoteType] = Field(default=None, title="Тип заметки")
    note_date: Optional[date] = Field(default=None, title="Дата заметки")
    linked_entity_ids: Optional[List[str]] = Field(default=None, title="Связанные сущности")
    is_template: Optional[bool] = Field(default=None, title="Шаблон")
    status: Optional[NoteStatus] = Field(default=None, title="Статус")
    visibility: Optional[NoteVisibility] = Field(default=None, title="Видимость")
    shared_with: Optional[List[str]] = Field(default=None, title="Поделено с")
    attachment_ids: Optional[List[str]] = Field(default=None, title="Прикрепленные файлы")


class NoteResponse(BaseModel):
    """Ответ с заметкой"""
    
    model_config = ConfigDict(from_attributes=True)
    
    note_id: str = Field(title="ID заметки", readonly=True)
    company_id: str = Field(title="ID компании", readonly=True)
    user_id: str = Field(title="ID автора", readonly=True)
    title: str = Field(title="Заголовок")
    content: str = Field(title="Содержимое")
    note_type: str = Field(title="Тип заметки")
    note_date: date = Field(title="Дата заметки")
    ai_summary: Optional[str] = Field(default=None, title="AI резюме")
    linked_entity_ids: List[str] = Field(default_factory=list, title="Связанные сущности")
    is_template: bool = Field(default=False, title="Шаблон")
    status: str = Field(default="published", title="Статус")
    visibility: str = Field(default="public", title="Видимость")
    shared_with: List[str] = Field(default_factory=list, title="Поделено с")
    attachment_ids: List[str] = Field(default_factory=list, title="Прикрепленные файлы")
    created_at: datetime = Field(title="Дата создания", readonly=True)
    updated_at: datetime = Field(title="Дата обновления", readonly=True)
    
    # Опционально: информация о связанных сущностях
    linked_entities: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        title="Связанные сущности (развернуто)"
    )


class NoteAnalyzeRequest(BaseModel):
    """Запрос анализа заметки AI"""
    
    model_config = ConfigDict(from_attributes=True)
    
    extract_entities: bool = Field(
        default=True,
        title="Извлечь сущности"
    )
    generate_summary: bool = Field(
        default=True,
        title="Сгенерировать резюме"
    )
    create_tasks: bool = Field(
        default=False,
        title="Создать задачи"
    )


class NoteAnalyzeResponse(BaseModel):
    """Ответ анализа заметки AI"""
    
    model_config = ConfigDict(from_attributes=True)
    
    summary: Optional[str] = Field(
        default=None,
        title="AI резюме"
    )
    extracted_entities: List[Dict[str, Any]] = Field(
        default_factory=list,
        title="Извлеченные сущности"
    )
    extracted_relationships: List[Dict[str, Any]] = Field(
        default_factory=list,
        title="Извлеченные связи"
    )
    created_tasks: List[Dict[str, Any]] = Field(
        default_factory=list,
        title="Созданные задачи"
    )



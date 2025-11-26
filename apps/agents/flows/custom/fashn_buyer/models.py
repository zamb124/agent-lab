"""
Модели данных для системы бота ассистента закупщика.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class ItemCondition(str, Enum):
    """Состояние вещи"""
    EXCELLENT = "excellent"  # отличное
    GOOD = "good"  # хорошее  
    FAIR = "fair"  # удовлетворительное
    POOR = "poor"  # плохое


class IssueStatus(str, Enum):
    """Статус заявки"""
    NEW = "new"  # новая, только создана
    NEED_INFO = "need_info"  # требуется уточнение у продавца
    ON_REVIEW = "on_review"  # на оценке/модерации
    CONFIRMED = "confirmed"  # заявка подтверждена
    CANCELED = "canceled"  # заявка отменена


class CommentRole(str, Enum):
    """Роль автора комментария"""
    REVIEWER = "reviewer"  # ревьювер/оценщик
    CLIENT = "client"  # клиент/продавец


class IssueComment(BaseModel):
    """Комментарий к заявке"""
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat(), description="Время создания")
    role: CommentRole = Field(..., description="Роль автора комментария")
    comment: str = Field(..., description="Текст комментария")


class DefectType(str, Enum):
    """Типы дефектов"""
    SCRATCHES = "scratches"  # царапины
    STAINS = "stains"  # пятна
    TEARS = "tears"  # разрывы
    WEAR = "wear"  # потертости
    HARDWARE_DAMAGE = "hardware_damage"  # повреждение фурнитуры
    COLOR_FADING = "color_fading"  # выцветание
    DEFORMATION = "deformation"  # деформация
    OTHER = "other"  # другое


class Defect(BaseModel):
    """Информация о дефекте"""
    type: DefectType = Field(..., description="Тип дефекта")
    description: str = Field(..., description="Описание дефекта")
    severity: int = Field(..., ge=1, le=5, description="Серьезность от 1 до 5")
    location: Optional[str] = Field(None, description="Расположение дефекта")


class ItemPhoto(BaseModel):
    """Фотография вещи"""
    file_id: str = Field(..., description="ID файла в системе")
    description: str = Field(..., description="Описание фото (общий вид, крупный план и т.д.)")
    is_main: bool = Field(default=False, description="Главное фото")


class FashnIssueCard(BaseModel):
    """Карточка вещи для закупки"""
    
    # Идентификаторы
    issue_id: str = Field(..., description="ID карточки")
    telegram_user_id: str = Field(..., description="Telegram ID пользователя")
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat(), description="Время создания")
    
    # Статус заявки
    status: IssueStatus = Field(default=IssueStatus.NEW, description="Статус заявки")
    
    # Основная информация о вещи
    item_name: str = Field(..., description="Название вещи (сумка, кофта и т.д.)")
    item_description: str = Field(..., description="Подробное описание вещи")
    brand: str = Field(..., description="Бренд")
    
    # Фотографии (минимум 3)
    photos: List[ItemPhoto] = Field(..., description="Фотографии вещи (минимум 3)")
    
    # Состояние и дефекты
    condition: ItemCondition = Field(..., description="Общее состояние вещи")
    defects: List[Defect] = Field(default_factory=list, description="Список дефектов")
    has_defects: bool = Field(default=False, description="Есть ли дефекты")
    
    # Цена
    desired_price: float = Field(..., gt=0, description="Желаемая цена продажи")
    currency: str = Field(default="RUB", description="Валюта")
    
    # Дополнительная информация
    additional_info: Optional[str] = Field(None, description="Дополнительная информация")
    
    # Комментарии и переписка
    comments: List[IssueComment] = Field(default_factory=list, description="Комментарии и переписка")
    
    # Метаданные
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Дополнительные метаданные")
    
    @field_validator('photos')
    @classmethod
    def validate_photos_count(cls, v):
        if len(v) < 3:
            raise ValueError('Необходимо минимум 3 фотографии')
        return v
    
    @property
    def storage_key(self) -> str:
        """Ключ для сохранения в storage"""
        return f"fashn_issue:{self.telegram_user_id}:{self.issue_id}"



"""
Wrapper модели для рекурсивного рендеринга в разных режимах
"""
from typing import List, Any, Dict
from pydantic import BaseModel
from app.frontend.field_extensions import Field

# Импортируем field_extensions чтобы monkey patch сработал
import app.frontend.field_extensions


class ModelListWrapper(BaseModel):
    """Wrapper для списка моделей - использует динамические шаблоны"""
    
    models: List[BaseModel] = Field(
        title="Модели",
        description="Список моделей для отображения",
        render=True
    )
    count: int = Field(title="Количество", hidden=True) 
    model_type: str = Field(title="Тип модели", hidden=True)
    
    class Config:
        # Переопределение шаблонов для разных режимов
        templates = {
            "table": "models/ModelListWrapper_table.html",  # Кастомный для таблицы
            "cards": "models/ModelListWrapper_cards.html",  # Кастомный для карточек
            # "form": None  # Нет шаблона - используется fallback
        }

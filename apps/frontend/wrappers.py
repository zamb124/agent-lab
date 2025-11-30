"""
Wrapper модели для рекурсивного рендеринга в разных режимах
"""

from typing import List
from pydantic import BaseModel, ConfigDict
from apps.frontend.field_extensions import Field


class ModelListWrapper(BaseModel):
    """Wrapper для списка моделей - использует динамические шаблоны"""
    
    model_config = ConfigDict(
        json_schema_extra={
            "templates": {
                "table": "models/ModelListWrapper_table.html",
                "cards": "models/ModelListWrapper_cards.html",
            }
        }
    )

    models: List[BaseModel] = Field(
        title="Модели", description="Список моделей для отображения", render=True
    )
    count: int = Field(title="Количество", hidden=True)
    model_type: str = Field(title="Тип модели", hidden=True)

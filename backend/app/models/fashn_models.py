"""
Pydantic модели для FASHN виртуальной примерки
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class TryOnParameters(BaseModel):
    """Параметры виртуальной примерки"""
    
    model_height_cm: float = Field(..., description="Рост модели в см")
    product_width_cm: float = Field(default=30, description="Ширина продукта в см")
    product_height_cm: float = Field(default=0, description="Высота продукта в см")
    item_kind: str = Field(default="bag", description="Тип продукта")
    placement: str = Field(default="left_shoulder", description="Размещение")
    offset_x_pct: float = Field(default=-6.0, description="Смещение по X в %")
    offset_y_pct: float = Field(default=0.0, description="Смещение по Y в %")
    visible_top_pct: float = Field(default=0.04, description="Верхний срез фигуры")
    visible_bottom_pct: float = Field(default=0.98, description="Нижний срез фигуры")
    scale_bias: float = Field(default=1.0, description="Множитель размера")
    variations: int = Field(default=0, description="Количество вариаций")


class TryOnRecord(BaseModel):
    """Запись виртуальной примерки"""
    
    id: str = Field(..., description="Уникальный ID примерки")
    user_id: str = Field(..., description="ID пользователя")
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat(), description="Время создания в ISO формате")
    
    # Исходные данные
    model_file_id: str = Field(..., description="ID файла фото пользователя")
    model_url: str = Field(..., description="URL фото пользователя")
    product_file_id: str = Field(..., description="ID файла изображения товара")
    product_image_url: str = Field(..., description="URL изображения товара")
    product_url: Optional[str] = Field(None, description="Исходный URL товара с сайта")
    
    # Результаты
    result_urls: List[str] = Field(..., description="URLs результатов примерки")
    
    # Параметры генерации
    parameters: TryOnParameters = Field(..., description="Параметры примерки")
    
    # Метаданные
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Дополнительные данные")


class TryOnHistoryResponse(BaseModel):
    """Ответ со списком примерок пользователя"""
    
    try_ons: List[TryOnRecord] = Field(..., description="Список примерок")
    total: int = Field(..., description="Общее количество примерок")
    page: int = Field(default=1, description="Номер страницы")
    limit: int = Field(default=20, description="Количество на странице")

"""
Модели для системы интернационализации.
"""

from enum import Enum
from typing import Dict, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class Language(str, Enum):
    """Поддерживаемые языки"""
    
    RU = "ru"
    EN = "en"


class TranslationKey(BaseModel):
    """Ключ перевода с контекстом и метаданными"""
    key: str = Field(description="Уникальный ключ перевода (например: models.user.fields.name)")
    context: Optional[str] = Field(default=None, description="Контекст использования ключа")
    source_file: Optional[str] = Field(default=None, description="Исходный файл где найден ключ")
    default_value: str = Field(description="Значение по умолчанию (обычно на русском)")
    category: str = Field(default="common", description="Категория ключа (models, common, errors, etc)")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "key": "models.user.fields.name",
                "context": "User model, field name",
                "source_file": "apps/flows/models/core_models.py",
                "default_value": "Имя пользователя",
                "category": "models"
            }
        }
    )


class Translation(BaseModel):
    """Перевод для конкретного языка"""
    language: Language = Field(description="Язык перевода")
    key: str = Field(description="Ключ перевода")
    value: str = Field(description="Переведенное значение")
    last_updated: datetime = Field(default_factory=datetime.now, description="Время последнего обновления")
    is_auto_generated: bool = Field(default=True, description="Сгенерировано автоматически или переведено вручную")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "language": "en",
                "key": "models.user.fields.name", 
                "value": "User Name",
                "is_auto_generated": False
            }
        }
    )


class TranslationSet(BaseModel):
    """Набор переводов для всех языков по одному ключу"""
    key: str = Field(description="Ключ перевода")
    translations: Dict[Language, str] = Field(default_factory=dict, description="Переводы на разные языки")
    context: Optional[str] = Field(default=None, description="Контекст использования")
    
    def get_translation(self, language: Language, fallback_language: Language = Language.RU) -> str:
        """Получить перевод с fallback"""
        return self.translations.get(language) or self.translations.get(fallback_language) or self.key


class TranslationFile(BaseModel):
    """Метаданные файла переводов"""
    language: Language = Field(description="Язык файла")
    version: str = Field(default="1.0.0", description="Версия файла переводов")
    last_updated: datetime = Field(default_factory=datetime.now, description="Время последнего обновления")
    completeness: float = Field(default=0.0, description="Процент завершенности переводов (0-100)")
    total_keys: int = Field(default=0, description="Общее количество ключей")
    translated_keys: int = Field(default=0, description="Количество переведенных ключей")
    
    def calculate_completeness(self) -> float:
        """Вычислить процент завершенности"""
        if self.total_keys == 0:
            return 100.0
        return (self.translated_keys / self.total_keys) * 100.0


class TranslationStats(BaseModel):
    """Статистика переводов"""
    total_languages: int = Field(description="Общее количество языков")
    total_keys: int = Field(description="Общее количество ключей")
    languages_stats: Dict[Language, TranslationFile] = Field(default_factory=dict, description="Статистика по языкам")
    
    def get_overall_completeness(self) -> float:
        """Общий процент завершенности всех переводов"""
        if not self.languages_stats:
            return 0.0
        
        total_completeness = sum(stats.calculate_completeness() for stats in self.languages_stats.values())
        return total_completeness / len(self.languages_stats)


class I18nConfig(BaseModel):
    """Конфигурация системы интернационализации"""
    default_language: Language = Field(default=Language.RU, description="Язык по умолчанию")
    fallback_language: Language = Field(default=Language.RU, description="Резервный язык")
    auto_generate_missing: bool = Field(default=True, description="Автоматически генерировать отсутствующие ключи")
    auto_generate_on_startup: bool = Field(default=True, description="Генерировать переводы при запуске приложения")
    scan_directories: List[str] = Field(
        default_factory=lambda: ["apps/flows/models", "apps/frontend"], 
        description="Директории для сканирования ключей"
    )
    translations_directory: str = Field(default="core/i18n", description="Директория с файлами переводов")


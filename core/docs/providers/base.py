"""
Базовый провайдер документации.
"""

from abc import ABC, abstractmethod
from typing import Dict, List

from core.docs.models import (
    CodeTemplate,
    DocumentationQuery,
    GlobalVariable,
    ModuleMethod,
    StateField,
)


class BaseDocProvider(ABC):
    """Базовый провайдер документации для языка."""
    
    language: str = "unknown"
    
    @abstractmethod
    def get_modules(self, query: DocumentationQuery) -> List[str]:
        """Список доступных модулей."""
        pass
    
    @abstractmethod
    def get_module_methods(self, query: DocumentationQuery) -> Dict[str, List[ModuleMethod]]:
        """Методы модулей."""
        pass
    
    @abstractmethod
    def get_globals(self, query: DocumentationQuery) -> List[GlobalVariable]:
        """Глобальные переменные."""
        pass
    
    @abstractmethod
    def get_builtins(self, query: DocumentationQuery) -> List[str]:
        """Встроенные функции."""
        pass
    
    @abstractmethod
    def get_templates(self, query: DocumentationQuery) -> List[CodeTemplate]:
        """Шаблоны кода."""
        pass
    
    def get_state_fields(self, query: DocumentationQuery) -> List[StateField]:
        """Поля state - общие для всех языков."""
        from core.docs.data.state_fields import STATE_FIELDS
        return [StateField(**f) for f in STATE_FIELDS]

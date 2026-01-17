"""
Сервис документации для редактора кода.
Поддерживает разные языки (Python, JavaScript) и фильтрацию.
"""

from core.docs.models import (
    DocumentationQuery,
    DocumentationResponse,
    GlobalVariable,
    StateField,
    CodeTemplate,
    ModuleMethod,
)
from core.docs.service import DocumentationService

__all__ = [
    "DocumentationQuery",
    "DocumentationResponse",
    "GlobalVariable",
    "StateField",
    "CodeTemplate",
    "ModuleMethod",
    "DocumentationService",
]

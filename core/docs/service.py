"""
Сервис документации с поддержкой разных языков и фильтров.
"""

from typing import Dict, Optional

from core.docs.models import (
    DocumentationQuery,
    DocumentationResponse,
)
from core.docs.markdown_builder import build_documentation_markdown
from core.docs.providers.base import BaseDocProvider
from core.docs.providers.python import PythonDocProvider


class DocumentationService:
    """
    Сервис документации для редактора кода.
    
    Поддерживает:
    - Разные языки (python, javascript, typescript)
    - Ракурсы (editor, agent, tool, node)
    - Фильтры (categories, groups, tags, node_type)
    """
    
    def __init__(self):
        self._providers: Dict[str, BaseDocProvider] = {
            "python": PythonDocProvider(),
        }
    
    def register_provider(self, language: str, provider: BaseDocProvider):
        """Регистрирует провайдер для языка."""
        self._providers[language] = provider
    
    def get_provider(self, language: str) -> Optional[BaseDocProvider]:
        """Возвращает провайдер для языка."""
        return self._providers.get(language)
    
    def query(self, q: DocumentationQuery) -> DocumentationResponse:
        """
        Основной метод - получить документацию по запросу.
        
        Args:
            q: Запрос с фильтрами и ракурсом
            
        Returns:
            DocumentationResponse с отфильтрованными данными
        """
        provider = self._providers.get(q.language)
        if not provider:
            raise ValueError(f"Unsupported language: {q.language}")
        
        response = DocumentationResponse(
            language=q.language,
            perspective=q.perspective,
        )
        
        if q.include_modules:
            response.modules = provider.get_modules(q)
            response.module_methods = {
                name: methods
                for name, methods in provider.get_module_methods(q).items()
            }
        
        if q.include_globals:
            response.globals = provider.get_globals(q)
        
        if q.include_builtins:
            response.builtins = provider.get_builtins(q)
        
        if q.include_state_fields:
            response.state_fields = provider.get_state_fields(q)
        
        if q.include_templates:
            response.templates = provider.get_templates(q)

        if q.include_platform_tools and q.platform_tools is not None:
            response.platform_tools = list(q.platform_tools)

        if q.runtime_namespace_extras is not None:
            response.runtime_namespace_extras = list(q.runtime_namespace_extras)

        return response

    def to_markdown(self, q: DocumentationQuery) -> str:
        """Тот же состав данных, что у query(), в виде одного Markdown-документа."""
        return build_documentation_markdown(self.query(q), query=q)
    
    def get_completions(self, language: str = "python", perspective: str = "editor"):
        """Удобный метод для получения данных autocomplete."""
        return self.query(DocumentationQuery(
            language=language,
            perspective=perspective,
        ))
    
    def get_templates(
        self,
        language: str = "python",
        node_type: Optional[str] = None,
        category: Optional[str] = None,
    ):
        """Удобный метод для получения шаблонов."""
        categories = [category] if category else None
        return self.query(DocumentationQuery(
            language=language,
            node_type=node_type,
            categories=categories,
            include_modules=False,
            include_globals=False,
            include_builtins=False,
            include_state_fields=False,
        )).templates


# Singleton instance
_service: Optional[DocumentationService] = None


def get_documentation_service() -> DocumentationService:
    """Возвращает singleton сервиса документации."""
    global _service
    if _service is None:
        _service = DocumentationService()
    return _service

"""
PromptResource - wrapper для prompt ресурса.

Предоставляет доступ к шаблонам промптов.
"""

from typing import Any, Dict

from core.logging import get_logger

logger = get_logger(__name__)


class PromptResource:
    """
    Ресурс для работы с шаблонами промптов.
    
    Пример:
        prompt = email_template.render(
            customer_name="John",
            order_id="12345"
        )
    """
    
    def __init__(
        self,
        template: str,
        variables: Dict[str, Any] = None,
    ):
        self.template = template
        self.default_variables = variables or {}
    
    def render(self, **kwargs) -> str:
        """
        Рендерит шаблон с переменными.
        
        Args:
            **kwargs: Переменные для шаблона
            
        Returns:
            Отрендеренный промпт
        """
        from jinja2 import Template
        
        # Мержим дефолтные переменные с переданными
        variables = {**self.default_variables, **kwargs}
        
        tpl = Template(self.template)
        return tpl.render(**variables)
    
    def __str__(self) -> str:
        """Возвращает шаблон как строку."""
        return self.template
    
    def __repr__(self) -> str:
        preview = self.template[:50] + "..." if len(self.template) > 50 else self.template
        return f"<PromptResource template='{preview}'>"

"""
Python провайдер документации.
"""

from typing import Dict, List

from core.docs.models import (
    CodeTemplate,
    DocumentationQuery,
    GlobalVariable,
    ModuleMethod,
    StateField,
)
from core.docs.providers.base import BaseDocProvider


from core.inline_python_eval_policy import ALLOWED_BUILTINS


class PythonDocProvider(BaseDocProvider):
    """Провайдер документации для Python."""
    
    language = "python"
    
    def get_modules(self, query: DocumentationQuery) -> List[str]:
        """Список доступных модулей."""
        from core.docs.data.python.modules import COMMON_MODULES
        return sorted(COMMON_MODULES)
    
    def get_module_methods(self, query: DocumentationQuery) -> Dict[str, List[ModuleMethod]]:
        """Методы модулей с фильтрацией."""
        from core.docs.data.python.modules import MODULE_METHODS
        
        result = {}
        for module_name, methods in MODULE_METHODS.items():
            result[module_name] = [
                ModuleMethod(
                    name=m["name"],
                    type=m["type"],
                    doc=m["doc"],
                )
                for m in methods
            ]
        return result
    
    def get_globals(self, query: DocumentationQuery) -> List[GlobalVariable]:
        """Глобальные переменные с фильтрацией по perspective и tags."""
        from core.docs.data.python.globals import GLOBALS
        
        result = []
        for g in GLOBALS:
            # Фильтрация по perspective
            perspectives = g.get("perspectives", [])
            if query.perspective and perspectives and query.perspective not in perspectives:
                continue
            
            # Фильтрация по tags
            item_tags = g.get("tags", [])
            if query.tags:
                if not any(t in item_tags for t in query.tags):
                    continue
            
            result.append(GlobalVariable(
                name=g["name"],
                type=g["type"],
                doc=g["doc"],
                perspective=perspectives,
                tags=item_tags,
            ))
        
        return result
    
    def get_builtins(self, query: DocumentationQuery) -> List[str]:
        """Встроенные имена, разрешённые в inline-коде flows (whitelist)."""
        return sorted(ALLOWED_BUILTINS)
    
    def get_templates(self, query: DocumentationQuery) -> List[CodeTemplate]:
        """Шаблоны кода с фильтрацией."""
        from core.docs.data.python.templates import CODE_TEMPLATES, FUNCTION_TEMPLATES
        
        # Выбор источника по node_type
        if query.node_type == "function":
            source = FUNCTION_TEMPLATES
        elif query.node_type == "tool":
            source = CODE_TEMPLATES
        else:
            source = CODE_TEMPLATES + FUNCTION_TEMPLATES
        
        result = []
        for t in source:
            # Фильтрация по category
            if query.categories and t["category"] not in query.categories:
                continue
            
            # Фильтрация по tags
            item_tags = t.get("tags", [])
            if query.tags:
                if not any(tag in item_tags for tag in query.tags):
                    continue
            
            result.append(CodeTemplate(
                id=t["id"],
                name=t["name"],
                description=t["description"],
                code=t["code"],
                category=t["category"],
                node_type=t.get("node_type", "tool"),
                tags=item_tags,
                language="python",
            ))
        
        return result
    
    def get_state_fields(self, query: DocumentationQuery) -> List[StateField]:
        """Поля state."""
        from core.docs.data.state_fields import STATE_FIELDS
        return [StateField(**f) for f in STATE_FIELDS]

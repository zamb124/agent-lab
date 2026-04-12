"""
CodeResourceProvider - провайдер для code ресурсов.
"""

from typing import Any, Dict

from apps.flows.src.models import ResourceDefinition, CodeResourceConfig
from apps.flows.src.resources.providers.base import BaseResourceProvider
from apps.flows.src.resources.wrappers import CodeModule
from core.logging import get_logger

logger = get_logger(__name__)


class CodeResourceProvider(BaseResourceProvider):
    """
    Провайдер для code ресурсов.
    
    Компилирует inline код и создаёт CodeModule с функциями/классами.
    """
    
    async def resolve(
        self,
        definition: ResourceDefinition,
        variables: Dict[str, Any],
    ) -> CodeModule:
        """
        Компилирует код и возвращает CodeModule.
        
        Args:
            definition: Определение ресурса с code конфигом
            variables: Переменные агента
            
        Returns:
            CodeModule с функциями/классами из кода
        """
        config = CodeResourceConfig.model_validate(definition.config)
        
        # language может быть enum или строка
        language = config.language.value if hasattr(config.language, 'value') else str(config.language)
        if language != "python":
            raise ValueError(f"Code resource only supports Python, got: {language}")
        
        # Компилируем код
        from apps.flows.src.container import get_container
        from apps.flows.src.eval.namespace import PythonNamespaceBuilder

        namespace_builder = PythonNamespaceBuilder(
            variables=variables,
            base_tool_class=get_container().base_tool_class,
        )
        namespace = namespace_builder.build()
        
        try:
            exec(config.code, namespace)
        except Exception as e:
            raise ValueError(f"Failed to compile code resource '{definition.resource_id}': {e}")
        
        # Извлекаем только пользовательские объекты
        user_namespace = {}
        builtin_names = set(namespace_builder.build().keys())
        
        for name, obj in namespace.items():
            if name not in builtin_names and not name.startswith("_"):
                user_namespace[name] = obj
        
        logger.debug(
            f"Code resource '{definition.resource_id}' loaded: {list(user_namespace.keys())}"
        )
        
        return CodeModule(namespace=user_namespace, source_code=config.code)

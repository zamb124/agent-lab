"""
BaseResourceProvider - базовый класс провайдера ресурсов.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict

from apps.flows.src.models import ResourceDefinition


class BaseResourceProvider(ABC):
    """
    Базовый класс провайдера ресурсов.
    
    Провайдер создаёт wrapper для использования в namespace.
    """
    
    @abstractmethod
    async def resolve(
        self,
        definition: ResourceDefinition,
        variables: Dict[str, Any],
    ) -> Any:
        """
        Резолвит ресурс и создаёт wrapper.
        
        Args:
            definition: Определение ресурса
            variables: Переменные агента для резолвинга @var:
            
        Returns:
            Wrapper объект для добавления в namespace
        """
        pass
    
    def _resolve_variable_refs(
        self,
        config: Dict[str, Any],
        variables: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Резолвит @var: ссылки в конфиге.
        
        Args:
            config: Конфиг с возможными @var: ссылками
            variables: Переменные для резолвинга
            
        Returns:
            Конфиг с резолвнутыми значениями
        """
        resolved = {}
        for key, value in config.items():
            if isinstance(value, str) and value.startswith("@var:"):
                var_name = value[5:]
                if var_name in variables:
                    resolved[key] = variables[var_name]
                else:
                    resolved[key] = value
            elif isinstance(value, dict):
                resolved[key] = self._resolve_variable_refs(value, variables)
            else:
                resolved[key] = value
        return resolved

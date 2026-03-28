"""
Сервис для управления переменными и секретами компании.
Поддерживает резолюцию @var:key ссылок.
"""

import logging
import re
from typing import Optional, Dict, Any, Set, List, TYPE_CHECKING

from core.db.repositories.variable_repository import Variable
from core.variables.resolver import VarResolver

if TYPE_CHECKING:
    from core.db.repositories.variable_repository import VariableRepository

logger = logging.getLogger(__name__)


class VariablesService:
    """Управление переменными компании с поддержкой ссылок @var:key"""
    
    def __init__(self, variable_repository: "VariableRepository"):
        """
        Args:
            variable_repository: Репозиторий для работы с переменными
        """
        self._variable_repository = variable_repository
    
    async def set_var(
        self, 
        key: str, 
        value: str, 
        is_secret: bool = False, 
        groups: list = None, 
        description: str = None
    ) -> bool:
        """
        Сохраняет переменную компании.
        
        Args:
            key: Ключ переменной
            value: Значение
            is_secret: Помечает как секрет (для UI)
            groups: Список групп/тегов для организации переменных
            description: Описание переменной
        
        Returns:
            True если сохранено
        """
        variable = Variable(
            key=key,
            value=value,
            secret=is_secret,
            groups=groups or [],
            description=description or ""
        )
        
        result = await self._variable_repository.set(variable)
        logger.info(f"Переменная сохранена: {key} (secret={is_secret}, groups={groups})")
        return result
    
    async def get_var(self, key: str) -> Optional[str]:
        """
        Получает переменную компании.
        
        Args:
            key: Ключ переменной
        Returns:
            Значение или None
        """
        variable = await self._variable_repository.get(key)
        
        if variable:
            return variable.value
        return None
    
    async def delete_var(self, key: str) -> bool:
        """Удаляет переменную компании"""
        return await self._variable_repository.delete(key)
    
    async def list_vars(self) -> Dict[str, Any]:
        """Получает все переменные компании"""
        all_variables = await self._variable_repository.get_all_variables()
        
        result = {}
        for key, variable in all_variables.items():
            result[key] = {
                "value": variable.value if not variable.secret else "***",
                "secret": variable.secret,
                "groups": variable.groups,
                "description": variable.description
            }
        
        return result
    
    async def resolve_variables(
        self, 
        text: str, 
        context_vars: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Резолвит @var:key ссылки в тексте.
        
        Args:
            text: Текст с возможными ссылками @var:key
            context_vars: Дополнительные переменные из контекста
            
        Returns:
            Текст с подставленными значениями
        """
        if not text:
            return text

        variables_map = await self._get_company_variables_map()
        if context_vars:
            variables_map = {**variables_map, **context_vars}
        return VarResolver.resolve_text(text, variables_map)
    
    async def get_all_resolved_vars(self) -> Dict[str, str]:
        """
        Получает все переменные компании с разрешенными ссылками.
        
        Returns:
            Словарь {key: resolved_value}
        """
        all_vars = await self.list_vars()
        
        resolved = {}
        for key, var_data in all_vars.items():
            if var_data.get("secret"):
                resolved[key] = "***"
            else:
                value = var_data["value"]
                resolved[key] = await self.resolve_variables(value, resolved)
        
        return resolved
    
    async def resolve(self, value: Any) -> Any:
        """
        Резолвит значение:
        - @var:key → загружает переменную компании
        - обычное значение → возвращает как есть
        - dict/list → рекурсивно резолвит все строки внутри
        
        Returns:
            Резолвнутое значение
        """
        variables_map = await self._get_company_variables_map()
        return VarResolver.resolve_deep(value, variables_map)

    async def _get_company_variables_map(self) -> Dict[str, Any]:
        """Возвращает словарь переменных компании в формате key -> value."""
        all_variables = await self._variable_repository.get_all_variables()
        return {key: variable.value for key, variable in all_variables.items()}
    
    def extract_variable_keys(self, value: Any) -> Set[str]:
        """
        Извлекает все ключи переменных из значения.
        
        Args:
            value: Значение (str, dict, list)
            
        Returns:
            Множество ключей переменных
        """
        keys = set()
        
        if isinstance(value, str):
            if value.startswith("@var:"):
                keys.add(value[5:])
            else:
                pattern = r'@var:(\w+)'
                matches = re.findall(pattern, value)
                keys.update(matches)
        
        elif isinstance(value, dict):
            for v in value.values():
                keys.update(self.extract_variable_keys(v))
        
        elif isinstance(value, list):
            for item in value:
                keys.update(self.extract_variable_keys(item))
        
        return keys
    
    async def add_tag_to_variable(self, var_key: str, tag: str) -> bool:
        """
        Добавляет тег к переменной (если переменная существует).
        
        Args:
            var_key: Ключ переменной
            tag: Тег для добавления
        
        Returns:
            True если тег добавлен
        """
        variable = await self.variable_repository.get(var_key)
        
        if not variable:
            logger.debug(f"Переменная {var_key} не найдена, пропускаем добавление тега {tag}")
            return False
        
        if tag not in variable.groups:
            variable.groups.append(tag)
            await self._variable_repository.set(variable)
            logger.info(f"Тег '{tag}' добавлен к переменной '{var_key}'")
            return True
        else:
            logger.debug(f"Тег '{tag}' уже существует для переменной '{var_key}'")
            return False
    
    async def tag_variables_for_entity(
        self, 
        entity_name: str, 
        data_sources: List[Any]
    ) -> int:
        """
        Добавляет теги к переменным используемым в сущности (агент/flow).
        
        Args:
            entity_name: Название сущности (имя агента или flow)
            data_sources: Список источников данных для поиска @var: ссылок
        
        Returns:
            Количество переменных с добавленными тегами
        """
        all_var_keys = set()
        
        for source in data_sources:
            if source:
                all_var_keys.update(self.extract_variable_keys(source))
        
        if not all_var_keys:
            logger.debug(f"Не найдено переменных @var: для {entity_name}")
            return 0
        
        logger.info(f"Найдено {len(all_var_keys)} переменных для {entity_name}: {all_var_keys}")
        
        tagged_count = 0
        for var_key in all_var_keys:
            if await self.add_tag_to_variable(var_key, entity_name):
                tagged_count += 1
        
        return tagged_count

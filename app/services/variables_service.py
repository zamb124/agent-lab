"""
Сервис для управления переменными и секретами компании.
Поддерживает резолюцию @var:key ссылок.
"""

import logging
import json
import re
from typing import Optional, Dict, Any, Set, List

from app.db.repositories import Storage

logger = logging.getLogger(__name__)


class VariablesService:
    """Управление переменными компании с поддержкой ссылок @var:key"""
    
    def __init__(self):
        self.storage = Storage()
    
    async def set_var(self, key: str, value: str, is_secret: bool = False, groups: list = None, description: str = None) -> bool:
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
        storage_key = f"var:{key}"
        
        await self.storage.set(storage_key, json.dumps({
            "value": value,
            "secret": is_secret,
            "groups": groups or [],
            "description": description or ""
        }))
        
        logger.info(f"✅ Переменная сохранена: {key} (secret={is_secret}, groups={groups})")
        return True
    
    async def get_var(self, key: str, create_if_missing: bool = False) -> Optional[str]:
        """
        Получает переменную компании.
        
        Args:
            key: Ключ переменной
            create_if_missing: Создать пустую переменную если не существует
        
        Returns:
            Значение или None
        """
        storage_key = f"var:{key}"
        data = await self.storage.get(storage_key)
        
        if data:
            var_data = json.loads(data)
            return var_data["value"]
        
        if create_if_missing:
            logger.warning(f"⚠️ Переменная {key} не найдена, создаем с пустым значением")
            await self.set_var(key, "", is_secret=False)
            return ""
        
        return None
    
    async def delete_var(self, key: str) -> bool:
        """Удаляет переменную компании"""
        storage_key = f"var:{key}"
        return await self.storage.delete(storage_key)
    
    async def list_vars(self) -> Dict[str, Any]:
        """Получает все переменные компании"""
        all_keys = await self.storage.list_by_prefix("var:")
        
        variables = {}
        for full_key in all_keys:
            # full_key = "company:test_company_1:var:test_key"
            # Извлекаем только имя переменной
            if ":var:" in full_key:
                var_key = full_key.split(":var:")[-1]
            else:
                var_key = full_key.split(":")[-1]
            
            # Используем force_global чтобы не добавлять префикс компании снова
            data = await self.storage.get(full_key, force_global=True)
            
            if data:
                var_data = json.loads(data)
                variables[var_key] = {
                    "value": var_data["value"] if not var_data.get("secret") else "***",
                    "secret": var_data.get("secret", False),
                    "groups": var_data.get("groups", []),
                    "description": var_data.get("description", "")
                }
        
        return variables
    
    async def resolve(self, value: Any, auto_create: bool = True) -> Any:
        """
        Резолвит значение:
        - @var:key → загружает переменную компании
        - обычное значение → возвращает как есть
        - dict/list → рекурсивно резолвит все строки внутри
        
        Args:
            value: Значение для резолюции
            auto_create: Автоматически создавать пустые переменные если не найдены
        
        Returns:
            Резолвнутое значение
        """
        if isinstance(value, str):
            if value.startswith("@var:"):
                var_key = value[5:]
                resolved = await self.get_var(var_key, create_if_missing=auto_create)
                if resolved is None:
                    raise ValueError(f"Variable {var_key} not found")
                return resolved
            return value
        
        elif isinstance(value, dict):
            return {k: await self.resolve(v, auto_create) for k, v in value.items()}
        
        elif isinstance(value, list):
            return [await self.resolve(item, auto_create) for item in value]
        
        else:
            return value
    
    def extract_variable_keys(self, value: Any) -> Set[str]:
        """
        Извлекает все ссылки на переменные (@var:key) из значения.
        
        Args:
            value: Значение для анализа (str, dict, list)
        
        Returns:
            Множество ключей переменных (без префикса @var:)
        """
        keys = set()
        
        if isinstance(value, str):
            # Ищем @var:key в строке
            matches = re.findall(r'@var:([a-zA-Z0-9_-]+)', value)
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
        storage_key = f"var:{var_key}"
        data = await self.storage.get(storage_key)
        
        if not data:
            logger.debug(f"Переменная {var_key} не найдена, пропускаем добавление тега {tag}")
            return False
        
        var_data = json.loads(data)
        groups = var_data.get("groups", [])
        
        if tag not in groups:
            groups.append(tag)
            var_data["groups"] = groups
            
            await self.storage.set(storage_key, json.dumps(var_data))
            logger.info(f"✅ Тег '{tag}' добавлен к переменной '{var_key}'")
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


# Глобальный экземпляр
_variables_service_instance = None


def get_variables_service() -> VariablesService:
    """Получает глобальный экземпляр VariablesService"""
    global _variables_service_instance
    if _variables_service_instance is None:
        _variables_service_instance = VariablesService()
    return _variables_service_instance


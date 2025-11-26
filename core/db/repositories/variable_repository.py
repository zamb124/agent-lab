"""
Репозиторий для работы с переменными.
Использует таблицу variables, is_global=False (изолирован по компаниям).
"""

import logging
from typing import Optional, Dict, List
from pydantic import BaseModel

from core.db.base_repository import BaseRepository
from core.db.storage import Storage

logger = logging.getLogger(__name__)


class VariableData(BaseModel):
    """Данные переменной (хранятся в БД без ключа)"""
    value: str
    secret: bool = False
    groups: List[str] = []
    description: str = ""


class Variable(BaseModel):
    """Модель переменной с ключом (используется в API)"""
    key: str
    value: str
    secret: bool = False
    groups: List[str] = []
    description: str = ""


class VariableRepository(BaseRepository[VariableData]):
    """
    Репозиторий для работы с переменными.
    is_global=False - переменные изолированы по компаниям.
    Хранит только данные (VariableData), ключ в storage key.
    """
    
    is_global = False

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=VariableData)

    def _get_key(self, key: str) -> str:
        return f"var:{key}"

    def _get_prefix(self) -> str:
        return "var:"

    def _get_table_name(self) -> str:
        return "variables"

    def _extract_entity_id(self, entity: VariableData) -> str:
        raise NotImplementedError("VariableRepository requires explicit key")
    
    async def get(self, key: str) -> Optional[Variable]:
        """Получает переменную с ключом"""
        base_key = self._get_key(key)
        final_key = self._build_final_key(base_key)
        table_name = self._get_table_name()
        
        data = await self._storage._get_with_session_and_table(final_key, table_name)
        if data is None:
            return None
        
        var_data = VariableData.model_validate_json(data)
        return Variable(
            key=key,
            value=var_data.value,
            secret=var_data.secret,
            groups=var_data.groups,
            description=var_data.description
        )
    
    async def set(self, entity: Variable) -> bool:
        """Сохраняет переменную (только данные, без ключа)"""
        var_data = VariableData(
            value=entity.value,
            secret=entity.secret,
            groups=entity.groups,
            description=entity.description
        )
        
        base_key = self._get_key(entity.key)
        final_key = self._build_final_key(base_key)
        table_name = self._get_table_name()
        
        data = var_data.model_dump_json()
        return await self._storage._set_with_table(final_key, data, table_name)
    
    async def delete(self, key: str) -> bool:
        """Удаляет переменную по ключу"""
        base_key = self._get_key(key)
        final_key = self._build_final_key(base_key)
        table_name = self._get_table_name()
        
        return await self._storage._delete_with_table(final_key, table_name)
    
    async def list_all(self, limit: int = 100) -> List[Variable]:
        """Возвращает список всех переменных с ключами"""
        base_prefix = self._get_prefix()
        final_prefix = self._build_final_key(base_prefix)
        table_name = self._get_table_name()
        
        all_data = await self._storage._get_all_by_prefix_and_table(
            final_prefix, table_name, limit
        )
        
        variables = []
        for full_key, data in all_data.items():
            try:
                var_key = full_key.split(":")[-1]
                var_data = VariableData.model_validate_json(data)
                variable = Variable(
                    key=var_key,
                    value=var_data.value,
                    secret=var_data.secret,
                    groups=var_data.groups,
                    description=var_data.description
                )
                variables.append(variable)
            except Exception as e:
                logger.error(f"Ошибка парсинга {full_key}: {e}")
                continue
        
        return variables

    async def get_all_variables(self, limit: int = 1000) -> Dict[str, Variable]:
        """
        Получает все переменные компании.
        
        Args:
            limit: Максимальное количество результатов
            
        Returns:
            Словарь {key: Variable}
        """
        all_vars = await self.list_all(limit=limit)
        return {var.key: var for var in all_vars}


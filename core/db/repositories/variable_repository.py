"""
Репозиторий для работы с переменными.
Использует таблицу variables, is_global=False (изолирован по компаниям).
"""

from __future__ import annotations

from pydantic import BaseModel

from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from core.logging import get_logger

logger = get_logger(__name__)


class VariableData(BaseModel):
    """Данные переменной (хранятся в БД без ключа)"""

    value: str
    secret: bool = False
    groups: list[str] = []
    description: str = ""


class Variable(BaseModel):
    """Модель переменной с ключом (используется в API)"""

    key: str
    value: str
    secret: bool = False
    groups: list[str] = []
    description: str = ""


class VariableRepository(BaseRepository[Variable]):
    """
    Репозиторий для работы с переменными.
    is_global=False - переменные изолированы по компаниям.
    Хранит только данные (VariableData), ключ в storage key.
    """

    is_global = False

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=Variable)

    def _get_key(self, entity_id: str) -> str:
        return f"var:{entity_id}"

    def _get_prefix(self) -> str:
        return "var:"

    def _get_table_name(self) -> str:
        return "variables"

    def _extract_entity_id(self, entity: Variable) -> str:
        return entity.key

    async def get(self, entity_id: str) -> Variable | None:
        """Получает переменную с ключом"""
        base_key = self._get_key(entity_id)
        final_key = self._build_final_key(base_key)
        table_name = self._get_table_name()

        data = await self._storage.get_with_session_and_table(final_key, table_name)
        if data is None:
            return None

        var_data = VariableData.model_validate_json(data)
        return Variable(
            key=entity_id,
            value=var_data.value,
            secret=var_data.secret,
            groups=var_data.groups,
            description=var_data.description,
        )

    async def set(self, entity: Variable) -> bool:
        """Сохраняет переменную (только данные, без ключа)"""
        var_data = VariableData(
            value=entity.value,
            secret=entity.secret,
            groups=entity.groups,
            description=entity.description,
        )

        base_key = self._get_key(entity.key)
        final_key = self._build_final_key(base_key)
        table_name = self._get_table_name()

        data = var_data.model_dump_json()
        return await self._storage.set_with_table(final_key, data, table_name)

    async def delete(self, entity_id: str) -> bool:
        """Удаляет переменную по ключу"""
        base_key = self._get_key(entity_id)
        final_key = self._build_final_key(base_key)
        table_name = self._get_table_name()

        return await self._storage.delete_with_table(final_key, table_name)

    async def list(self, *, limit: int, offset: int = 0) -> list[Variable]:
        """Возвращает страницу переменных с ключами."""
        base_prefix = self._get_prefix()
        final_prefix = self._build_final_key(base_prefix)
        table_name = self._get_table_name()

        all_data = await self._storage.get_all_by_prefix_and_table(
            final_prefix, table_name, limit, offset
        )

        variables: list[Variable] = []
        for full_key, data in all_data.items():
            try:
                var_key = full_key.split(":")[-1]
                var_data = VariableData.model_validate_json(data)
                variable = Variable(
                    key=var_key,
                    value=var_data.value,
                    secret=var_data.secret,
                    groups=var_data.groups,
                    description=var_data.description,
                )
                variables.append(variable)
            except Exception as e:
                logger.error(f"Ошибка парсинга {full_key}: {e}")
                continue

        return variables

    async def get_variables(self, *, limit: int = 1000, offset: int = 0) -> dict[str, Variable]:
        """Словарь {key: Variable} для текущей компании."""
        variables = await self.list(limit=limit, offset=offset)
        return {var.key: var for var in variables}

    async def get_many(self, entity_ids: list[str]) -> dict[str, Variable]:
        """Получает несколько переменных по списку ключей."""
        result: dict[str, Variable] = {}
        for entity_id in entity_ids:
            variable = await self.get(entity_id)
            if variable is not None:
                result[entity_id] = variable
        return result

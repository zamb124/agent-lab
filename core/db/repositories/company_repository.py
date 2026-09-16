"""
Репозиторий для работы с Company.
Использует shared БД, is_global=True (не изолирован по компаниям).
"""

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import ClassVar, override

from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from core.logging import get_logger
from core.models.identity_models import Company

logger = get_logger(__name__)


class CompanyRepository(BaseRepository[Company]):
    """
    Репозиторий для работы с компаниями.
    is_global=True - компании не изолированы (это метаданные самих компаний).
    """

    is_global: ClassVar[bool] = True

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=Company)

    @override
    def _get_key(self, company_id: str) -> str:
        return f"company:{company_id}"

    @override
    def _get_prefix(self) -> str:
        return "company:"

    @override
    def _get_table_name(self) -> str:
        return "storage"

    @override
    def _extract_entity_id(self, entity: Company) -> str:
        return entity.company_id

    async def put_member_roles(
        self,
        company_id: str,
        user_id: str,
        roles: Sequence[str],
    ) -> Company:
        """Пишет `members[user_id]` под FOR UPDATE, не затирая остальных членов."""
        if not company_id.strip():
            raise ValueError("company_id is required")
        if not user_id.strip():
            raise ValueError("user_id is required")
        normalized = [role.strip() for role in roles if role.strip()]
        if not normalized:
            raise ValueError("company membership roles must be non-empty")

        def mutate(company: Company) -> None:
            company.members[user_id] = list(normalized)

        return await self._mutate_locked(company_id, mutate)

    async def discard_member(self, company_id: str, user_id: str) -> Company:
        """Снимает `members[user_id]` под FOR UPDATE, не затирая остальных членов."""
        if not company_id.strip():
            raise ValueError("company_id is required")
        if not user_id.strip():
            raise ValueError("user_id is required")

        def mutate(company: Company) -> None:
            _ = company.members.pop(user_id, None)

        return await self._mutate_locked(company_id, mutate)

    async def _mutate_locked(
        self,
        company_id: str,
        mutate: Callable[[Company], None],
    ) -> Company:
        final_key = self._build_final_key(self._get_key(company_id))
        async with self._storage.get_session() as session:
            raw = await self._storage.get(
                final_key,
                db_session=session,
                force_global=True,
                for_update=True,
            )
            if raw is None:
                raise ValueError(f"company not found: {company_id}")
            company = Company.model_validate_json(raw)
            mutate(company)
            company.updated_at = datetime.now(timezone.utc)
            _ = await self._storage.set(
                final_key,
                company.model_dump_json(),
                db_session=session,
                force_global=True,
            )
            await session.commit()
            return company

    @override
    async def list(self, *, limit: int, offset: int = 0) -> list[Company]:
        """
        Возвращает только сущности Company из shared storage.

        В таблице `storage` соседствуют ключи других репозиториев
        (`company:<id>:embed_config:...`, и т.д.), поэтому фильтруем
        только ключи каноничного формата `company:<company_id>`.
        """
        prefix = self._get_prefix()
        table_name = self._get_table_name()
        all_data = await self._storage.get_all_by_prefix_and_table(prefix, table_name, limit, offset)

        entities: list[Company] = []
        for key, data in all_data.items():
            # Ключ компании должен содержать ровно одно двоеточие: "company:<id>"
            if key.count(":") != 1:
                continue
            try:
                entity = self.model_class.model_validate_json(data)
                entities.append(entity)
            except Exception as e:
                logger.error(f"Ошибка парсинга {key}: {e}")
                continue
        return entities

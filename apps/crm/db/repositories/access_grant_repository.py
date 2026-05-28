"""
Репозиторий для AccessGrants.
"""

from typing import override

from sqlalchemy import and_, delete, func, or_, select, update

from apps.crm.db.base import BaseCRMRepository, CRMDatabase
from apps.crm.db.models import AccessGrant
from core.db.utils import get_rowcount


class AccessGrantRepository(BaseCRMRepository[AccessGrant]):
    """Репозиторий для работы с AccessGrants"""

    def __init__(self, db: CRMDatabase):
        super().__init__(db)

    @property
    @override
    def model_class(self) -> type[AccessGrant]:
        return AccessGrant

    @property
    @override
    def id_field(self) -> str:
        return "grant_id"

    async def find_by_resource(
        self, resource_type: str, resource_id: str, resource_company_id: str | None = None
    ) -> list[AccessGrant]:
        """
        Найти все гранты для ресурса.

        Аргументы:
            resource_company_id: ID компании ресурса (не запрашивающего пользователя!)
                                Если None, ищет во всех компаниях
        """
        async with self._db.session() as session:
            query = (
                select(AccessGrant)
                .where(AccessGrant.resource_type == resource_type)
                .where(AccessGrant.resource_id == resource_id)
            )

            if resource_company_id:
                query = query.where(AccessGrant.company_id == resource_company_id)

            result = await session.execute(query)
            return list(result.scalars().all())

    async def count_by_resource(
        self,
        resource_type: str,
        resource_id: str,
        resource_company_id: str | None = None,
    ) -> int:
        async with self._db.session() as session:
            stmt = (
                select(func.count())
                .select_from(AccessGrant)
                .where(AccessGrant.resource_type == resource_type)
                .where(AccessGrant.resource_id == resource_id)
            )
            if resource_company_id:
                stmt = stmt.where(AccessGrant.company_id == resource_company_id)
            result = await session.execute(stmt)
            return result.scalar() or 0

    async def remap_entity_resource_id(
        self,
        company_id: str,
        old_entity_id: str,
        new_entity_id: str,
    ) -> int:
        """Для resource_type=entity заменяет resource_id при слиянии сущностей."""
        if old_entity_id == new_entity_id:
            raise ValueError("old_entity_id и new_entity_id должны различаться")
        async with self._db.session() as session:
            result = await session.execute(
                update(AccessGrant)
                .where(
                    AccessGrant.company_id == company_id,
                    AccessGrant.resource_type == "entity",
                    AccessGrant.resource_id == old_entity_id,
                )
                .values(resource_id=new_entity_id)
            )
            await session.commit()
            return get_rowcount(result)

    async def deduplicate_entity_grants(self, company_id: str, entity_id: str) -> None:
        """
        Удаляет дубликаты грантов на одну entity после remap:
        один ключ (grant_type, target_user_id, target_company_id, role).
        """
        grants = await self.find_by_resource("entity", entity_id, resource_company_id=company_id)
        seen: dict[tuple[str, str | None, str | None, str], str] = {}
        to_delete: list[str] = []
        for g in grants:
            if g.company_id != company_id:
                continue
            key = (g.grant_type, g.target_user_id, g.target_company_id, g.role)
            if key not in seen:
                seen[key] = g.grant_id
                continue
            to_delete.append(g.grant_id)
        if not to_delete:
            return
        async with self._db.session() as session:
            for gid in to_delete:
                result = await session.execute(
                    delete(AccessGrant).where(AccessGrant.grant_id == gid)
                )
                if get_rowcount(result) != 1:
                    raise ValueError(f"Access grant {gid} was not deleted")
            await session.commit()

    async def find_by_resources_batch(
        self,
        resource_keys: list[tuple[str, str]],
    ) -> dict[tuple[str, str], list[AccessGrant]]:
        """
        Пакетная загрузка грантов для набора (resource_type, resource_id).
        Возвращает словарь {(resource_type, resource_id): [grants]}.
        """
        if not resource_keys:
            return {}
        async with self._db.session() as session:
            conditions = [
                and_(
                    AccessGrant.resource_type == rtype,
                    AccessGrant.resource_id == rid,
                )
                for rtype, rid in resource_keys
            ]
            stmt = select(AccessGrant).where(or_(*conditions))
            result = await session.execute(stmt)
            grants = list(result.scalars().all())

        grants_map: dict[tuple[str, str], list[AccessGrant]] = {k: [] for k in resource_keys}
        for grant in grants:
            key = (grant.resource_type, grant.resource_id)
            if key in grants_map:
                grants_map[key].append(grant)
        return grants_map

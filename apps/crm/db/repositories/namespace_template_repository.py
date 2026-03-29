"""Репозиторий шаблонов namespace и их типов."""

from typing import Optional
from uuid import uuid4

from sqlalchemy import delete, select

from apps.crm.db.base import BaseCRMRepository, CRMDatabase
from apps.crm.db.models import NamespaceTemplate, NamespaceTemplateType


class NamespaceTemplateRepository(BaseCRMRepository[NamespaceTemplate]):
    @property
    def model_class(self) -> type[NamespaceTemplate]:
        return NamespaceTemplate

    @property
    def id_field(self) -> str:
        return "template_key"

    async def list_for_company(self, company_id: Optional[str] = None) -> list[NamespaceTemplate]:
        effective_company_id = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(NamespaceTemplate).where(
                NamespaceTemplate.company_id == effective_company_id
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_by_template_id(
        self,
        template_id: str,
        company_id: Optional[str] = None
    ) -> Optional[NamespaceTemplate]:
        effective_company_id = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(NamespaceTemplate).where(
                NamespaceTemplate.company_id == effective_company_id,
                NamespaceTemplate.template_id == template_id,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def create_template(
        self,
        template_id: str,
        name: str,
        description: Optional[str],
        icon: Optional[str] = None,
        company_id: Optional[str] = None,
        is_system: bool = False,
    ) -> NamespaceTemplate:
        template = NamespaceTemplate(
            template_key=str(uuid4()),
            company_id=company_id or self._get_company_id(),
            template_id=template_id,
            name=name,
            description=description,
            icon=icon,
            is_system=is_system,
        )
        return await self.create(template)

    async def list_types(self, template_key: str) -> list[NamespaceTemplateType]:
        async with self._db.session() as session:
            stmt = select(NamespaceTemplateType).where(
                NamespaceTemplateType.template_key == template_key
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_type(self, template_key: str, type_id: str) -> Optional[NamespaceTemplateType]:
        async with self._db.session() as session:
            stmt = select(NamespaceTemplateType).where(
                NamespaceTemplateType.template_key == template_key,
                NamespaceTemplateType.type_id == type_id,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def upsert_type(
        self,
        template_key: str,
        type_id: str,
        parent_type_id: Optional[str],
        name: str,
        description: Optional[str],
        prompt: Optional[str],
        required_fields: dict[str, object],
        optional_fields: dict[str, object],
        icon: Optional[str],
        color: Optional[str],
        is_event: bool,
        check_duplicates: bool,
        weight_coefficient: float,
        namespace_ids: list[str],
    ) -> NamespaceTemplateType:
        async with self._db.session() as session:
            stmt = select(NamespaceTemplateType).where(
                NamespaceTemplateType.template_key == template_key,
                NamespaceTemplateType.type_id == type_id,
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing is None:
                existing = NamespaceTemplateType(
                    entry_id=str(uuid4()),
                    template_key=template_key,
                    type_id=type_id,
                )
            existing.parent_type_id = parent_type_id
            existing.name = name
            existing.description = description
            existing.prompt = prompt
            existing.required_fields = required_fields
            existing.optional_fields = optional_fields
            existing.icon = icon
            existing.color = color
            existing.is_event = is_event
            existing.check_duplicates = check_duplicates
            existing.weight_coefficient = weight_coefficient
            existing.namespace_ids = namespace_ids
            session.add(existing)
            await session.commit()
            await session.refresh(existing)
            return existing

    async def delete_type(self, template_key: str, type_id: str) -> bool:
        async with self._db.session() as session:
            stmt = delete(NamespaceTemplateType).where(
                NamespaceTemplateType.template_key == template_key,
                NamespaceTemplateType.type_id == type_id,
            )
            result = await session.execute(stmt)
            await session.commit()
            return bool(result.rowcount)

    async def delete_template_with_types(self, template_key: str) -> bool:
        return await self.delete(template_key)


def get_namespace_template_repository(db: CRMDatabase) -> NamespaceTemplateRepository:
    return NamespaceTemplateRepository(db)

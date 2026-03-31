"""
Сущность contact на графе CRM, соответствующая пользователю платформы.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid

from apps.crm.constants_graph import PLATFORM_USER_ID_ATTR
from apps.crm.db.models import CRMEntity
from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from core.db.repositories.user_repository import UserRepository
from core.logging import get_logger

logger = get_logger(__name__)

USER_PERSON_NAMESPACE = "default"


class UserPersonService:
    """Создание и обновление contact-сущности для пользователя платформы."""

    def __init__(
        self,
        entity_repo: EntityRepository,
        entity_type_repo: EntityTypeRepository,
        user_repository: UserRepository,
    ) -> None:
        self._entity_repo = entity_repo
        self._entity_type_repo = entity_type_repo
        self._user_repository = user_repository

    async def get_or_create_person_entity_id(
        self,
        user_id: str,
        company_id: str,
    ) -> str:
        user = await self._user_repository.get(user_id)
        if user is None:
            raise ValueError(f"User not found: {user_id}")

        crm_block: Dict[str, Any] = dict(user.attrs.get("crm") or {})
        by_company: Dict[str, str] = dict(crm_block.get("person_entity_by_company") or {})
        existing_id = by_company.get(company_id)
        if existing_id:
            existing = await self._entity_repo.get(existing_id)
            if existing is not None and existing.company_id == company_id:
                await self._sync_person_fields_from_user(existing, user)
                return existing_id

        contact_type = await self._entity_type_repo.get_by_type_id("contact")
        if contact_type is None:
            raise ValueError("Тип сущности contact не найден для компании (инициализация CRM?)")

        display = self._display_name_from_user(user)
        attributes: Dict[str, Any] = {
            PLATFORM_USER_ID_ATTR: user_id,
        }
        if user.first_name:
            attributes["first_name"] = user.first_name
        if user.last_name:
            attributes["last_name"] = user.last_name

        entity = CRMEntity(
            user_id=user_id,
            entity_id=str(uuid.uuid4()),
            entity_type="contact",
            entity_subtype=None,
            name=display,
            description=user.bio,
            attributes=attributes,
            tags=[],
            company_id=company_id,
            namespace=USER_PERSON_NAMESPACE,
        )
        await self._entity_repo.create(entity)

        by_company[company_id] = entity.entity_id
        crm_block["person_entity_by_company"] = by_company
        merged_attrs = dict(user.attrs)
        merged_attrs["crm"] = crm_block
        user.attrs = merged_attrs
        user.updated_at = datetime.now(timezone.utc)
        await self._user_repository.set(user)

        logger.info(f"Created person entity {entity.entity_id} for user {user_id}")
        return entity.entity_id

    async def record_last_voice_entity(
        self,
        user_id: str,
        namespace: str,
        voice_entity_id: str,
    ) -> None:
        user = await self._user_repository.get(user_id)
        if user is None:
            raise ValueError(f"User not found: {user_id}")
        crm_block: Dict[str, Any] = dict(user.attrs.get("crm") or {})
        last_map: Dict[str, str] = dict(crm_block.get("last_voice_entity_id_by_namespace") or {})
        last_map[namespace] = voice_entity_id
        crm_block["last_voice_entity_id_by_namespace"] = last_map
        merged = dict(user.attrs)
        merged["crm"] = crm_block
        user.attrs = merged
        user.updated_at = datetime.now(timezone.utc)
        await self._user_repository.set(user)

    async def format_user_profile_for_ai(self, user_id: str) -> str:
        user = await self._user_repository.get(user_id)
        if user is None:
            raise ValueError(f"User not found: {user_id}")
        lines: list[str] = []
        fn = getattr(user, "first_name", None)
        ln = getattr(user, "last_name", None)
        if (fn and str(fn).strip()) or (ln and str(ln).strip()):
            lines.append(
                "Имя и фамилия: "
                + " ".join(p for p in [str(fn or "").strip(), str(ln or "").strip()] if p)
            )
        lines.append(f"Отображаемое имя: {user.name}")
        if user.bio and str(user.bio).strip():
            lines.append(f"О себе: {user.bio.strip()}")
        return "\n".join(lines)

    async def resolve_last_voice_entity_id(
        self,
        user_id: str,
        company_id: str,
        namespace: str,
    ) -> Optional[str]:
        user = await self._user_repository.get(user_id)
        if user is None:
            raise ValueError(f"User not found: {user_id}")
        crm_block: Dict[str, Any] = dict(user.attrs.get("crm") or {})
        last_map: Dict[str, str] = dict(crm_block.get("last_voice_entity_id_by_namespace") or {})
        eid = last_map.get(namespace)
        if not eid:
            return None
        ent = await self._entity_repo.get(eid)
        if ent is None or ent.company_id != company_id:
            return None
        if ent.entity_type != "contact":
            return None
        return eid

    @staticmethod
    def _display_name_from_user(user: Any) -> str:
        parts: list[str] = []
        if getattr(user, "first_name", None) and str(user.first_name).strip():
            parts.append(str(user.first_name).strip())
        if getattr(user, "last_name", None) and str(user.last_name).strip():
            parts.append(str(user.last_name).strip())
        if parts:
            return " ".join(parts)
        if getattr(user, "name", None) and str(user.name).strip():
            return str(user.name).strip()
        raise ValueError("У пользователя нет имени для сущности contact")

    async def _sync_person_fields_from_user(self, entity: CRMEntity, user: Any) -> None:
        next_name = self._display_name_from_user(user)
        attrs = dict(entity.attributes or {})
        attrs[PLATFORM_USER_ID_ATTR] = user.user_id
        if user.first_name:
            attrs["first_name"] = user.first_name
        if user.last_name:
            attrs["last_name"] = user.last_name
        changed = entity.name != next_name or entity.description != user.bio or attrs != (entity.attributes or {})
        if not changed:
            return
        entity.name = next_name
        entity.description = user.bio
        entity.attributes = attrs
        entity.updated_at = datetime.now(timezone.utc)
        await self._entity_repo.update(entity)

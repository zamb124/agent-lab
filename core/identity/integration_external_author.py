"""
Сопоставление внешнего автора интеграции (например пользователь AmoCRM) с user_id платформы.

Профиль пользователя хранится только в user:{id} (shared users). Ключи integration_ext_author:*
в той же таблице storage — это индекс внешний_id → user_id, без дублирования email в отдельной модели.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from core.models.identity_models import User

if TYPE_CHECKING:
    from core.db.repositories.company_repository import CompanyRepository
    from core.db.repositories.user_repository import UserRepository
    from core.db.storage import Storage

MAP_PREFIX = "integration_ext_author"
PREPROVISION_ROLE = "viewer"


def integration_external_author_storage_key(
    company_id: str,
    provider_id: str,
    account_key: str,
    external_user_id: str,
) -> str:
    return f"{MAP_PREFIX}:{company_id}:{provider_id}:{account_key}:{external_user_id}"


def _merge_roles(existing: list[str], role: str) -> list[str]:
    return list(dict.fromkeys([*existing, role]))


class IntegrationExternalAuthorService:
    def __init__(
        self,
        *,
        storage: Storage,
        user_repository: UserRepository,
        company_repository: CompanyRepository,
    ) -> None:
        self._storage = storage
        self._user_repository = user_repository
        self._company_repository = company_repository

    async def resolve_platform_user_id(
        self,
        *,
        company_id: str,
        provider_id: str,
        account_key: str,
        external_user_id: str,
        email: str,
        display_name: str | None = None,
    ) -> str:
        ext = str(external_user_id).strip()
        if not ext:
            raise ValueError("external_user_id обязателен")
        email_norm = email.strip().lower()
        if not email_norm:
            raise ValueError("email обязателен для привязки внешнего автора")
        prov = str(provider_id).strip()
        if not prov:
            raise ValueError("provider_id обязателен")
        acc = str(account_key).strip()
        if not acc:
            raise ValueError("account_key обязателен")

        key = integration_external_author_storage_key(company_id, prov, acc, ext)
        cached = await self._storage.get(key, force_global=True)
        if cached:
            data = json.loads(cached)
            uid_raw = data.get("user_id")
            if not isinstance(uid_raw, str) or not uid_raw.strip():
                raise ValueError(f"Повреждённая запись маппинга: {key}")
            uid = uid_raw.strip()
            existing = await self._user_repository.get(uid)
            if existing is not None:
                return uid
            await self._storage.delete(key, force_global=True)

        matches = await self._user_repository.find_all_by_email_ci(email_norm)
        if len(matches) > 1:
            raise ValueError(
                f"Несколько пользователей с email {email_norm}: "
                f"{', '.join(u.user_id for u in matches)}"
            )

        company = await self._company_repository.get(company_id)
        if company is None:
            raise ValueError(f"Компания не найдена: {company_id}")

        if len(matches) == 1:
            user = matches[0]
            await self._ensure_company_membership(
                user=user, company_id=company_id, company=company
            )
            user.updated_at = datetime.now(timezone.utc)
            await self._user_repository.set(user)
            await self._company_repository.set(company)
        else:
            user_id = f"user_{uuid.uuid4().hex[:12]}"
            nm = (display_name or "").strip() or email_norm
            user = User(
                user_id=user_id,
                name=nm,
                emails=[email_norm],
                companies={company_id: [PREPROVISION_ROLE]},
                active_company_id=company_id,
            )
            mr = company.members.get(user.user_id, [])
            company.members[user.user_id] = _merge_roles(mr, PREPROVISION_ROLE)
            await self._user_repository.set(user)
            await self._company_repository.set(company)

        await self._storage.set(
            key,
            json.dumps({"user_id": user.user_id}),
            force_global=True,
        )
        return user.user_id

    async def _ensure_company_membership(
        self,
        *,
        user: User,
        company_id: str,
        company,
    ) -> None:
        cr = user.companies.get(company_id, [])
        user.companies[company_id] = _merge_roles(cr, PREPROVISION_ROLE)
        if not (user.active_company_id or "").strip():
            user.active_company_id = company_id
        mr = company.members.get(user.user_id, [])
        company.members[user.user_id] = _merge_roles(mr, PREPROVISION_ROLE)

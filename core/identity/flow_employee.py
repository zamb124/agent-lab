"""Flow-as-employee identity: flow становится полноценным User платформы.

Flow с включённым employee-режимом — это обычный ``User`` в ``user_repository`` и
``company.members`` (двустороннее членство), со статусом, ролями, группами и
куратором-человеком. Всё, что платформа умеет для пользователя (RBAC, ACL, sync
membership, назначение задач, биллинг-атрибуция, user-chip), работает для него без
адаптеров — потому что это и есть пользователь.

Ось идентичности агента одна: ``user_id``. Отдельной сущности Agent нет.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from core.authz.company_sync import remove_company_member
from core.container.base import BaseContainer
from core.identity.company_membership import (
    remove_company_membership,
    sync_existing_company_member,
)
from core.identity.runtime_users import ensure_persisted_runtime_user
from core.models.identity_models import User, UserStatus
from core.types import JsonObject

FLOW_EMPLOYEE_KIND = "flow_employee"
FLOW_EMPLOYEE_USER_ID_PREFIX = "flow_employee_"
FLOW_EMPLOYEE_FLOW_ID_ATTR = "flow_id"
FLOW_EMPLOYEE_CURATORS_ATTR = "curator_user_ids"
_KIND_ATTR = "kind"


def flow_employee_user_id(flow_id: str) -> str:
    """Канонический ``user_id`` сотрудника-агента для данного flow."""
    clean = flow_id.strip()
    if not clean:
        raise ValueError("flow_employee_user_id: flow_id must be non-empty")
    return f"{FLOW_EMPLOYEE_USER_ID_PREFIX}{clean}"


def is_flow_employee(user: User) -> bool:
    """User является flow-сотрудником."""
    return user.attributes.get(_KIND_ATTR) == FLOW_EMPLOYEE_KIND


def is_flow_employee_user_id(user_id: str) -> bool:
    """Быстрая проверка по каноническому формату id (без загрузки User)."""
    return user_id.startswith(FLOW_EMPLOYEE_USER_ID_PREFIX)


def require_flow_employee_flow_id(user: User) -> str:
    """flow_id сотрудника-агента; ошибка, если User им не является."""
    if not is_flow_employee(user):
        raise ValueError(f"require_flow_employee_flow_id: user {user.user_id} is not a flow employee")
    raw = user.attributes.get(FLOW_EMPLOYEE_FLOW_ID_ATTR)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"flow employee {user.user_id} has no flow_id attribute")
    return raw


def flow_employee_curator_user_ids(user: User) -> list[str]:
    """Кураторы-люди сотрудника-агента (ответственные, получатели эскалаций)."""
    if not is_flow_employee(user):
        raise ValueError(f"flow_employee_curator_user_ids: user {user.user_id} is not a flow employee")
    raw = user.attributes.get(FLOW_EMPLOYEE_CURATORS_ATTR)
    if not isinstance(raw, list):
        raise ValueError(f"flow employee {user.user_id} has no curator_user_ids attribute")
    curators: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip() and item not in curators:
            curators.append(item)
    if not curators:
        raise ValueError(f"flow employee {user.user_id} has empty curator_user_ids")
    return curators


def _clean_curators(curator_user_ids: Sequence[str]) -> list[str]:
    curators: list[str] = []
    for raw in curator_user_ids:
        value = raw.strip()
        if value and value not in curators:
            curators.append(value)
    if not curators:
        raise ValueError("flow employee requires at least one curator_user_id")
    return curators


async def ensure_flow_employee(
    container: BaseContainer,
    *,
    flow_id: str,
    company_id: str,
    name: str,
    roles: Sequence[str],
    curator_user_ids: Sequence[str],
    avatar_url: str | None = None,
) -> User:
    """Создаёт/обновляет сотрудника-агента с двусторонним членством в компании.

    Пишет обе стороны членства (``user.companies`` и ``company.members``), чтобы
    сотрудник был виден в team API, sync company_members и mention-автокомплите.
    """
    clean_flow_id = flow_id.strip()
    if not clean_flow_id:
        raise ValueError("ensure_flow_employee: flow_id must be non-empty")
    clean_company_id = company_id.strip()
    if not clean_company_id:
        raise ValueError("ensure_flow_employee: company_id must be non-empty")
    curators = _clean_curators(curator_user_ids)
    user_id = flow_employee_user_id(clean_flow_id)

    attributes: JsonObject = {
        _KIND_ATTR: FLOW_EMPLOYEE_KIND,
        FLOW_EMPLOYEE_FLOW_ID_ATTR: clean_flow_id,
        FLOW_EMPLOYEE_CURATORS_ATTR: list(curators),
    }
    user = await ensure_persisted_runtime_user(
        container,
        user_id=user_id,
        company_id=clean_company_id,
        name=name,
        roles=roles,
        attributes=attributes,
    )

    now = datetime.now(timezone.utc)
    user_changed = False
    if user.status != UserStatus.ACTIVE:
        user.status = UserStatus.ACTIVE
        user_changed = True
    clean_name = name.strip()
    if clean_name and user.name != clean_name:
        user.name = clean_name
        user_changed = True
    normalized_avatar = avatar_url.strip() if avatar_url is not None else None
    if normalized_avatar and user.avatar_url != normalized_avatar:
        user.avatar_url = normalized_avatar
        user_changed = True
    if user_changed:
        user.updated_at = now
        _ = await container.user_repository.set(user)

    company = await container.company_repository.get(clean_company_id)
    if company is None:
        raise ValueError(f"ensure_flow_employee: company {clean_company_id} not found")
    existing_member_roles = company.members.get(user_id, [])
    merged_member_roles = list(dict.fromkeys([*existing_member_roles, *user.companies[clean_company_id]]))
    if merged_member_roles != existing_member_roles:
        stored = await container.company_repository.put_member_roles(
            clean_company_id,
            user_id,
            merged_member_roles,
        )
        company.members = stored.members
        company.updated_at = stored.updated_at
    await sync_existing_company_member(
        authz=container.authz_service,
        company_id=clean_company_id,
        user_id=user_id,
        roles=merged_member_roles,
    )

    return user


async def deactivate_flow_employee(
    container: BaseContainer,
    *,
    flow_id: str,
    company_id: str,
) -> None:
    """Деактивирует сотрудника-агента: статус INACTIVE + снятие членства в компании.

    Запись ``User`` сохраняется для аудита (created entities, сообщения, задачи).
    """
    clean_flow_id = flow_id.strip()
    clean_company_id = company_id.strip()
    if not clean_flow_id or not clean_company_id:
        raise ValueError("deactivate_flow_employee: flow_id and company_id required")
    user_id = flow_employee_user_id(clean_flow_id)
    now = datetime.now(timezone.utc)

    user = await container.user_repository.get(user_id)
    company = await container.company_repository.get(clean_company_id)
    if user is not None and company is not None and (
        clean_company_id in user.companies or user_id in company.members
    ):
        if user.status != UserStatus.INACTIVE:
            user.status = UserStatus.INACTIVE
            user.updated_at = now
        await remove_company_membership(
            company_repository=container.company_repository,
            user_repository=container.user_repository,
            authz=container.authz_service,
            company=company,
            user=user,
            allow_empty_companies=True,
        )
        return

    if user is not None:
        changed = False
        if user.status != UserStatus.INACTIVE:
            user.status = UserStatus.INACTIVE
            changed = True
        if clean_company_id in user.companies:
            del user.companies[clean_company_id]
            changed = True
        if changed:
            user.updated_at = now
            _ = await container.user_repository.set(user)

    if company is not None and user_id in company.members:
        del company.members[user_id]
        company.updated_at = now
        _ = await container.company_repository.set(company)
        await remove_company_member(
            container.authz_service,
            company_id=clean_company_id,
            user_id=user_id,
        )

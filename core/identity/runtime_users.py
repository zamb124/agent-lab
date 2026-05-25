"""Helpers for runtime identities that must survive service boundaries."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from core.container.base import BaseContainer
from core.models.identity_models import User, UserStatus
from core.types import JsonObject


def _clean_roles(roles: Sequence[str]) -> list[str]:
    out: list[str] = []
    for role in roles:
        value = role.strip()
        if value and value not in out:
            out.append(value)
    if not out:
        raise ValueError("runtime user roles must be non-empty")
    return out


async def ensure_persisted_runtime_user(
    container: BaseContainer,
    *,
    user_id: str,
    company_id: str,
    name: str,
    roles: Sequence[str],
    attributes: JsonObject | None = None,
    email: str | None = None,
) -> User:
    """
    Persist a restricted runtime user so cross-service tool execution can restore Context.

    The flow runtime can carry in-memory identities, but capability/tool-runtime
    boundaries intentionally rebuild Context from repositories. Runtime users
    used across those boundaries must therefore exist in ``user_repository``.
    """
    clean_user_id = user_id.strip()
    clean_company_id = company_id.strip()
    if not clean_user_id:
        raise ValueError("runtime user_id must be non-empty")
    if not clean_company_id:
        raise ValueError("runtime company_id must be non-empty")
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("runtime user name must be non-empty")

    clean_roles = _clean_roles(roles)
    now = datetime.now(timezone.utc)
    existing = await container.user_repository.get(clean_user_id)
    runtime_attrs: JsonObject = dict(attributes) if attributes is not None else {}
    runtime_attrs["runtime_identity"] = True

    if existing is not None:
        changed = False
        existing_roles = (
            list(existing.companies[clean_company_id])
            if clean_company_id in existing.companies
            else []
        )
        merged_roles = list(dict.fromkeys([*existing_roles, *clean_roles]))
        if merged_roles != existing_roles:
            existing.companies[clean_company_id] = merged_roles
            changed = True
        merged_groups = list(dict.fromkeys([*existing.groups, *clean_roles]))
        if merged_groups != existing.groups:
            existing.groups = merged_groups
            changed = True
        if not existing.active_company_id:
            existing.active_company_id = clean_company_id
            changed = True
        merged_attrs = {**existing.attributes, **runtime_attrs}
        if merged_attrs != existing.attributes:
            existing.attributes = merged_attrs
            changed = True
        if changed:
            existing.updated_at = now
            _ = await container.user_repository.set(existing)
        return existing

    clean_email = email.strip() if email is not None else ""
    emails = [clean_email] if clean_email else []
    user = User(
        user_id=clean_user_id,
        name=clean_name,
        status=UserStatus.ACTIVE,
        groups=clean_roles,
        companies={clean_company_id: clean_roles},
        active_company_id=clean_company_id,
        emails=emails,
        attributes=runtime_attrs,
        created_at=now,
        updated_at=now,
    )
    _ = await container.user_repository.set(user)
    return user

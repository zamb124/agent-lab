"""Helpers for runtime identities that must survive service boundaries."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Protocol, cast

from core.models.identity_models import User, UserStatus


class _UserRepository(Protocol):
    async def get(self, entity_id: str) -> User | None: ...

    async def set(self, entity: User) -> bool: ...


def _clean_roles(roles: Sequence[str] | None, *, fallback: str) -> list[str]:
    out: list[str] = []
    for role in roles or []:
        value = str(role).strip()
        if value and value not in out:
            out.append(value)
    if not out:
        out.append(fallback)
    return out


async def ensure_persisted_runtime_user(
    container: object,
    *,
    user_id: str,
    company_id: str,
    name: str,
    roles: Sequence[str] | None,
    attrs: dict[str, Any] | None = None,
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

    user_repository = cast(_UserRepository, getattr(container, "user_repository"))
    clean_roles = _clean_roles(roles, fallback="guest")
    now = datetime.now(timezone.utc)
    existing = await user_repository.get(clean_user_id)
    runtime_attrs = dict(attrs or {})
    runtime_attrs["runtime_identity"] = True

    if existing is not None:
        changed = False
        existing_roles = list(existing.companies.get(clean_company_id) or [])
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
        merged_attrs = {**existing.attrs, **runtime_attrs}
        if merged_attrs != existing.attrs:
            existing.attrs = merged_attrs
            changed = True
        if changed:
            existing.updated_at = now
            _ = await user_repository.set(existing)
        return existing

    emails = [email.strip()] if isinstance(email, str) and email.strip() else []
    user = User(
        user_id=clean_user_id,
        name=name.strip() or clean_user_id,
        status=UserStatus.ACTIVE,
        groups=clean_roles,
        companies={clean_company_id: clean_roles},
        active_company_id=clean_company_id,
        emails=emails,
        attrs=runtime_attrs,
        created_at=now,
        updated_at=now,
    )
    _ = await user_repository.set(user)
    return user

"""
Единый платформенный сервис namespace.

Единственное место конструирования записи `Namespace` и её персистентности.
Все сервисы (CRM, Sync, Office, RAG, core) читают и создают namespace только
через этот сервис поверх `NamespaceRepository` (shared БД). Прямое
конструирование `Namespace(...)` + `namespace_repository.set(...)` в остальном
коде запрещено — это ломает единый источник правды.
"""

from __future__ import annotations

from core.context import require_active_company
from core.db.repositories.namespace_repository import NamespaceRepository
from core.models.identity_models import (
    Namespace,
    NamespaceCRMSettings,
    NamespaceKind,
    NamespaceSyncSettings,
)

_DEFAULT_NAMESPACE_NAME = "default"
_DEFAULT_NAMESPACE_DESCRIPTION = "Основное пространство"

_TECHNICAL_NAME_PREFIXES: tuple[str, ...] = (
    "office-catalog-",
    "llm-memory-",
)

_PRODUCT_LIST_KINDS: frozenset[NamespaceKind] = frozenset(
    {
        NamespaceKind.COMPANY_WORKSPACE,
        NamespaceKind.PERSONAL,
    }
)


def personal_namespace_name(user_id: str) -> str:
    """Стабильный slug personal namespace: user-{user_id}."""
    cleaned = user_id.strip()
    if cleaned == "":
        raise ValueError("user_id is required for personal namespace name")
    return f"user-{cleaned}"


def infer_namespace_kind(name: str, *, explicit: NamespaceKind | None = None) -> NamespaceKind:
    """Определяет kind по явному аргументу или эвристике имени (technical prefixes)."""
    if explicit is not None:
        return explicit
    for prefix in _TECHNICAL_NAME_PREFIXES:
        if name.startswith(prefix):
            return NamespaceKind.TECHNICAL
    if name.startswith("user-"):
        return NamespaceKind.PERSONAL
    return NamespaceKind.COMPANY_WORKSPACE


class NamespaceService:
    """Единый вход жизненного цикла записи namespace для всех сервисов."""

    def __init__(self, repository: NamespaceRepository) -> None:
        self._repository: NamespaceRepository = repository

    async def get(self, name: str) -> Namespace | None:
        """Читает namespace по имени в scope активной компании."""
        return await self._repository.get(name)

    async def list(
        self,
        *,
        limit: int,
        offset: int = 0,
        kinds: frozenset[NamespaceKind] | None = None,
    ) -> list[Namespace]:
        """
        Страница namespace компании.

        kinds=None → product list (company_workspace + personal, без technical).
        """
        if offset == 0 and await self._repository.get(_DEFAULT_NAMESPACE_NAME) is None:
            _ = await self.ensure_default()
        allowed = kinds if kinds is not None else _PRODUCT_LIST_KINDS
        # KV list не умеет SQL-filter по kind — читаем страницу с запасом и фильтруем.
        fetch_limit = min(max(limit * 4, limit), 500)
        raw = await self._repository.list(limit=fetch_limit, offset=offset)
        filtered = [ns for ns in raw if ns.kind in allowed]
        return filtered[:limit]

    async def list_by_company(
        self,
        company_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
        kinds: frozenset[NamespaceKind] | None = None,
    ) -> list[Namespace]:
        """Список namespace компании (company_id обязан совпадать с активной)."""
        if offset == 0 and await self._repository.get(_DEFAULT_NAMESPACE_NAME) is None:
            _ = await self.ensure_default()
        allowed = kinds if kinds is not None else _PRODUCT_LIST_KINDS
        raw = await self._repository.list_by_company(company_id, limit=limit, offset=offset)
        return [ns for ns in raw if ns.kind in allowed]

    async def list_company_workspaces(
        self, *, limit: int = 200, offset: int = 0
    ) -> list[Namespace]:
        """Только company_workspace (CRM/Sync/Office picker)."""
        return await self.list(
            limit=limit,
            offset=offset,
            kinds=frozenset({NamespaceKind.COMPANY_WORKSPACE}),
        )

    async def count(self, *, kinds: frozenset[NamespaceKind] | None = None) -> int:
        """Число namespace компании с фильтром kind."""
        allowed = kinds if kinds is not None else _PRODUCT_LIST_KINDS
        all_items = await self._repository.list(limit=1000, offset=0)
        return sum(1 for ns in all_items if ns.kind in allowed)

    async def ensure_default(self) -> Namespace:
        """Идемпотентно гарантирует системный default namespace текущей компании."""
        existing = await self._repository.get(_DEFAULT_NAMESPACE_NAME)
        if existing is not None:
            return await self._migrate_legacy_kind(existing)
        company_id = require_active_company().company_id
        namespace = Namespace(
            name=_DEFAULT_NAMESPACE_NAME,
            company_id=company_id,
            description=_DEFAULT_NAMESPACE_DESCRIPTION,
            is_default=True,
            kind=NamespaceKind.COMPANY_WORKSPACE,
        )
        _ = await self._repository.set(namespace)
        return namespace

    async def ensure_personal_namespace(
        self,
        user_id: str,
        *,
        display_name: str,
    ) -> Namespace:
        """
        Идемпотентно гарантирует personal namespace member'а в активной компании.

        slug = user-{user_id}; description = display_name (именная подпись).
        """
        cleaned_user_id = user_id.strip()
        if cleaned_user_id == "":
            raise ValueError("user_id is required")
        cleaned_display = display_name.strip()
        if cleaned_display == "":
            raise ValueError("display_name is required for personal namespace")

        name = personal_namespace_name(cleaned_user_id)
        existing = await self._repository.get(name)
        if existing is not None:
            if existing.kind != NamespaceKind.PERSONAL:
                raise ValueError(f"Namespace {name} exists but is not personal")
            if existing.owner_user_id != cleaned_user_id:
                raise ValueError(f"Namespace {name} owner mismatch")
            if existing.description != cleaned_display:
                updated = existing.model_copy(
                    update={"description": cleaned_display},
                )
                _ = await self._repository.set(updated)
                return updated
            return existing

        company_id = require_active_company().company_id
        namespace = Namespace(
            name=name,
            company_id=company_id,
            description=cleaned_display,
            is_default=False,
            kind=NamespaceKind.PERSONAL,
            owner_user_id=cleaned_user_id,
        )
        _ = await self._repository.set(namespace)
        return namespace

    async def create(
        self,
        *,
        name: str,
        description: str | None = None,
        is_default: bool = False,
        kind: NamespaceKind = NamespaceKind.COMPANY_WORKSPACE,
        owner_user_id: str | None = None,
        crm_settings: NamespaceCRMSettings | None = None,
        sync_settings: NamespaceSyncSettings | None = None,
    ) -> Namespace:
        """Создаёт новую запись namespace; падает, если namespace уже существует."""
        if kind == NamespaceKind.PERSONAL:
            raise ValueError(
                "personal namespace must be created via ensure_personal_namespace"
            )
        resolved_kind = infer_namespace_kind(name, explicit=kind)
        if await self._repository.get(name) is not None:
            raise ValueError(f"Namespace {name} already exists")
        company_id = require_active_company().company_id
        namespace = Namespace(
            name=name,
            company_id=company_id,
            description=description,
            is_default=is_default,
            kind=resolved_kind,
            owner_user_id=owner_user_id,
            crm_settings=crm_settings,
            sync_settings=sync_settings,
        )
        _ = await self._repository.set(namespace)
        return namespace

    async def get_or_create(
        self,
        name: str,
        *,
        description: str | None = None,
        is_default: bool = False,
        kind: NamespaceKind | None = None,
        owner_user_id: str | None = None,
        crm_settings: NamespaceCRMSettings | None = None,
        sync_settings: NamespaceSyncSettings | None = None,
    ) -> Namespace:
        """Возвращает namespace, создавая его при отсутствии (идемпотентно)."""
        existing = await self._repository.get(name)
        if existing is not None:
            return await self._migrate_legacy_kind(existing, preferred_kind=kind)
        resolved_kind = infer_namespace_kind(name, explicit=kind)
        if resolved_kind == NamespaceKind.PERSONAL:
            if owner_user_id is None:
                raise ValueError("owner_user_id required to create personal namespace")
            display = description if description is not None and description.strip() != "" else owner_user_id
            return await self.ensure_personal_namespace(
                owner_user_id,
                display_name=display,
            )
        company_id = require_active_company().company_id
        namespace = Namespace(
            name=name,
            company_id=company_id,
            description=description,
            is_default=is_default,
            kind=resolved_kind,
            owner_user_id=None,
            crm_settings=crm_settings,
            sync_settings=sync_settings,
        )
        _ = await self._repository.set(namespace)
        return namespace

    async def ensure_exists(self, name: str) -> Namespace:
        """
        Гарантирует существование namespace для потребителя.

        Системный `default` создаётся автоматически; любое другое отсутствующее
        имя — ошибка (без тихого fallback).
        """
        existing = await self._repository.get(name)
        if existing is None and name == _DEFAULT_NAMESPACE_NAME:
            existing = await self.ensure_default()
        if existing is None:
            raise ValueError(f"Namespace not found: {name}")
        return await self._migrate_legacy_kind(existing)

    async def save(self, namespace: Namespace) -> Namespace:
        """Персистит уже загруженную/изменённую запись namespace."""
        _ = await self._repository.set(namespace)
        return namespace

    async def delete(self, name: str) -> bool:
        """Удаляет запись namespace из реестра."""
        return await self._repository.delete(name)

    async def _migrate_legacy_kind(
        self,
        namespace: Namespace,
        *,
        preferred_kind: NamespaceKind | None = None,
    ) -> Namespace:
        """
        Дописывает kind/owner для записей, созданных до введения kind.

        Pydantic default уже company_workspace; technical/personal по имени.
        """
        inferred = infer_namespace_kind(namespace.name, explicit=preferred_kind)
        needs_save = False
        updates: dict[str, NamespaceKind | str | None] = {}
        if namespace.kind != inferred and (
            preferred_kind is not None
            or namespace.kind == NamespaceKind.COMPANY_WORKSPACE
            and inferred != NamespaceKind.COMPANY_WORKSPACE
        ):
            updates["kind"] = inferred
            needs_save = True
        if inferred == NamespaceKind.PERSONAL and namespace.owner_user_id is None:
            prefix = "user-"
            if namespace.name.startswith(prefix):
                updates["owner_user_id"] = namespace.name[len(prefix) :]
                updates["kind"] = NamespaceKind.PERSONAL
                needs_save = True
        if not needs_save:
            return namespace
        migrated = namespace.model_copy(update=updates)
        _ = await self._repository.set(migrated)
        return migrated

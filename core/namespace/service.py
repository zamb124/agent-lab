"""
Единый платформенный сервис namespace.

Единственное место конструирования записи `Namespace` и её персистентности.
Все сервисы читают и создают namespace только через этот сервис.
Запросы строки — методы `Namespace`.
"""

from __future__ import annotations

from core.authz.models import AuthzObject
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation
from core.context import require_active_company
from core.errors.boundary import PlatformNotFoundError
from core.models.identity_models import (
    Namespace,
    NamespaceCRMSettings,
    NamespaceKind,
    NamespaceSyncSettings,
)
from core.namespace.authz.tuples import (
    platform_namespace_company_editor_tuple,
    platform_namespace_company_link,
    platform_namespace_company_viewer_tuple,
    platform_namespace_owner_tuple,
)

_DEFAULT_NAMESPACE_NAME = "default"
_DEFAULT_NAMESPACE_DESCRIPTION = "Основное пространство"

TECHNICAL_NAMESPACE_NAME_PREFIXES: tuple[str, ...] = (
    "office-catalog-",
    "llm-memory-",
    "wiki-restricted-",
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
    for prefix in TECHNICAL_NAMESPACE_NAME_PREFIXES:
        if name.startswith(prefix):
            return NamespaceKind.TECHNICAL
    if name.startswith("user-"):
        return NamespaceKind.PERSONAL
    return NamespaceKind.COMPANY_WORKSPACE


class NamespaceService:
    """Единый вход жизненного цикла записи namespace для всех сервисов."""

    def __init__(
        self,
        authz_service: AuthzService,
    ) -> None:
        self._authz: AuthzService = authz_service

    async def _save_row(self, namespace: Namespace) -> bool:
        if namespace.company_id == "" or namespace.name == "":
            raise ValueError("namespace company_id and name are required")
        namespace.namespace_id = f"{namespace.company_id}:{namespace.name}"
        return await Namespace.set(namespace)

    async def get(self, name: str) -> Namespace | None:
        """Читает namespace по имени в scope активной компании."""
        return await Namespace.by_name(name)

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
        if offset == 0 and await Namespace.by_name(_DEFAULT_NAMESPACE_NAME) is None:
            _ = await self.ensure_default()
        allowed = kinds if kinds is not None else _PRODUCT_LIST_KINDS
        return await Namespace.list_by_kind(
            list(allowed),
            limit=limit,
            offset=offset,
        )

    async def list_by_company(
        self,
        company_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
        kinds: frozenset[NamespaceKind] | None = None,
    ) -> list[Namespace]:
        """Список namespace компании (company_id обязан совпадать с активной)."""
        active_company_id = require_active_company().company_id
        if company_id != active_company_id:
            raise ValueError("company_id does not match the active company")
        return await self.list(limit=limit, offset=offset, kinds=kinds)

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
        return await Namespace.count_by_kind(list(allowed))

    async def ensure_default(self) -> Namespace:
        """Идемпотентно гарантирует системный default namespace текущей компании."""
        existing = await Namespace.by_name(_DEFAULT_NAMESPACE_NAME)
        if existing is not None:
            migrated = await self._migrate_legacy_kind(existing)
            await self._ensure_platform_namespace_authz(migrated)
            return migrated
        company_id = require_active_company().company_id
        namespace = Namespace(
            name=_DEFAULT_NAMESPACE_NAME,
            company_id=company_id,
            description=_DEFAULT_NAMESPACE_DESCRIPTION,
            is_default=True,
            kind=NamespaceKind.COMPANY_WORKSPACE,
        )
        return await self._persist_new_namespace(namespace)

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
        existing = await Namespace.by_name(name)
        if existing is not None:
            if existing.kind != NamespaceKind.PERSONAL:
                raise ValueError(f"Namespace {name} exists but is not personal")
            if existing.owner_user_id != cleaned_user_id:
                raise ValueError(f"Namespace {name} owner mismatch")
            if existing.description != cleaned_display:
                updated = existing.model_copy(
                    update={"description": cleaned_display},
                )
                _ = await self._save_row(updated)
                await self._ensure_platform_namespace_authz(updated)
                return updated
            await self._ensure_platform_namespace_authz(existing)
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
        return await self._persist_new_namespace(namespace)

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
        if await Namespace.by_name(name) is not None:
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
        return await self._persist_new_namespace(namespace)

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
        existing = await Namespace.by_name(name)
        if existing is not None:
            migrated = await self._migrate_legacy_kind(existing, preferred_kind=kind)
            await self._ensure_platform_namespace_authz(migrated)
            return migrated
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
        return await self._persist_new_namespace(namespace)

    async def ensure_exists(self, name: str) -> Namespace:
        """
        Гарантирует существование namespace для потребителя.

        Системный `default` создаётся автоматически; любое другое отсутствующее
        имя — ошибка (без тихого fallback).
        """
        existing = await Namespace.by_name(name)
        if existing is None and name == _DEFAULT_NAMESPACE_NAME:
            existing = await self.ensure_default()
        if existing is None:
            raise ValueError(f"Namespace not found: {name}")
        migrated = await self._migrate_legacy_kind(existing)
        await self._ensure_platform_namespace_authz(migrated)
        return migrated

    async def set_sync_settings(
        self, name: str, sync_settings: NamespaceSyncSettings | None
    ) -> Namespace:
        existing = await self.get(name)
        if existing is None:
            raise PlatformNotFoundError(f"Namespace {name} not found", error_code="not_found")
        existing.sync_settings = sync_settings
        return await self.save(existing)

    async def save(self, namespace: Namespace) -> Namespace:
        """Персистит уже загруженную/изменённую запись namespace и FGA tuples."""
        _ = await self._save_row(namespace)
        await self._ensure_platform_namespace_authz(namespace)
        return namespace

    async def delete(self, name: str) -> bool:
        """Удаляет запись namespace из реестра и OpenFGA tuples."""
        existing = await Namespace.by_name(name)
        if existing is None:
            return False
        deletes = await self._authz.list_tuples(
            AuthzObject.platform_namespace(existing.company_id, existing.name)
        )
        if deletes:
            await self._authz.delete(deletes)
        return await Namespace.delete_by_name(name)

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
        _ = await self._save_row(migrated)
        try:
            await self._write_platform_namespace_authz(migrated)
        except Exception:
            _ = await self._save_row(namespace)
            raise
        return migrated

    async def _persist_new_namespace(self, namespace: Namespace) -> Namespace:
        _ = await self._save_row(namespace)
        try:
            await self._write_platform_namespace_authz(namespace)
        except Exception:
            _ = await Namespace.delete_by_name(namespace.name)
            raise
        return namespace

    async def _ensure_platform_namespace_authz(self, namespace: Namespace) -> None:
        """Дописывает company/viewer/editor[/owner] tuples, если SQL есть, а FGA нет."""
        obj = AuthzObject.platform_namespace(namespace.company_id, namespace.name)
        existing = await self._authz.list_tuples(obj)
        relations = {item.relation for item in existing}
        needed = {
            AuthzRelation.COMPANY,
            AuthzRelation.VIEWER,
            AuthzRelation.EDITOR,
        }
        if namespace.kind == NamespaceKind.PERSONAL:
            needed.add(AuthzRelation.OWNER)
        if needed.issubset(relations):
            return
        await self._write_platform_namespace_authz(namespace)

    async def _write_platform_namespace_authz(self, namespace: Namespace) -> None:
        writes = [
            platform_namespace_company_link(namespace.company_id, namespace.name),
            platform_namespace_company_viewer_tuple(
                namespace.company_id, namespace.name
            ),
            platform_namespace_company_editor_tuple(
                namespace.company_id, namespace.name
            ),
        ]
        if namespace.kind == NamespaceKind.PERSONAL:
            if namespace.owner_user_id is None:
                raise ValueError(
                    f"personal namespace {namespace.name} requires owner_user_id"
                )
            writes.append(
                platform_namespace_owner_tuple(
                    namespace.company_id,
                    namespace.name,
                    namespace.owner_user_id,
                )
            )
        await self._authz.write(writes)

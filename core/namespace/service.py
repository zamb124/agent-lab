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
    NamespaceSyncSettings,
)

_DEFAULT_NAMESPACE_NAME = "default"
_DEFAULT_NAMESPACE_DESCRIPTION = "Основное пространство"


class NamespaceService:
    """Единый вход жизненного цикла записи namespace для всех сервисов."""

    def __init__(self, repository: NamespaceRepository) -> None:
        self._repository: NamespaceRepository = repository

    async def get(self, name: str) -> Namespace | None:
        """Читает namespace по имени в scope активной компании."""
        return await self._repository.get(name)

    async def list(self, *, limit: int, offset: int = 0) -> list[Namespace]:
        """Возвращает страницу namespace компании, гарантируя системный default."""
        if offset == 0 and await self._repository.get(_DEFAULT_NAMESPACE_NAME) is None:
            _ = await self.ensure_default()
        return await self._repository.list(limit=limit, offset=offset)

    async def list_by_company(
        self, company_id: str, *, limit: int = 200, offset: int = 0
    ) -> list[Namespace]:
        """Список namespace компании (company_id обязан совпадать с активной)."""
        if offset == 0 and await self._repository.get(_DEFAULT_NAMESPACE_NAME) is None:
            _ = await self.ensure_default()
        return await self._repository.list_by_company(company_id, limit=limit, offset=offset)

    async def count(self) -> int:
        """Число namespace компании."""
        return await self._repository.count_all()

    async def ensure_default(self) -> Namespace:
        """Идемпотентно гарантирует системный default namespace текущей компании."""
        existing = await self._repository.get(_DEFAULT_NAMESPACE_NAME)
        if existing is not None:
            return existing
        company_id = require_active_company().company_id
        namespace = Namespace(
            name=_DEFAULT_NAMESPACE_NAME,
            company_id=company_id,
            description=_DEFAULT_NAMESPACE_DESCRIPTION,
            is_default=True,
        )
        _ = await self._repository.set(namespace)
        return namespace

    async def create(
        self,
        *,
        name: str,
        description: str | None = None,
        is_default: bool = False,
        crm_settings: NamespaceCRMSettings | None = None,
        sync_settings: NamespaceSyncSettings | None = None,
    ) -> Namespace:
        """Создаёт новую запись namespace; падает, если namespace уже существует."""
        if await self._repository.get(name) is not None:
            raise ValueError(f"Namespace {name} already exists")
        company_id = require_active_company().company_id
        namespace = Namespace(
            name=name,
            company_id=company_id,
            description=description,
            is_default=is_default,
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
        crm_settings: NamespaceCRMSettings | None = None,
        sync_settings: NamespaceSyncSettings | None = None,
    ) -> Namespace:
        """Возвращает namespace, создавая его при отсутствии (идемпотентно)."""
        existing = await self._repository.get(name)
        if existing is not None:
            return existing
        company_id = require_active_company().company_id
        namespace = Namespace(
            name=name,
            company_id=company_id,
            description=description,
            is_default=is_default,
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
        return existing

    async def save(self, namespace: Namespace) -> Namespace:
        """Персистит уже загруженную/изменённую запись namespace."""
        _ = await self._repository.set(namespace)
        return namespace

    async def delete(self, name: str) -> bool:
        """Удаляет запись namespace из реестра."""
        return await self._repository.delete(name)

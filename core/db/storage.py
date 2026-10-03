"""Ключ-значение в таблице ``storage``.

Алиас базы выбирается по URL: ``shared``, ``tracing`` или ``default``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import NewType

from core.config import get_settings
from core.db.request_scope_kv_cache import invalidate_key, lookup_memoized, set_memoized
from core.logging import get_logger
from core.models.context_models import Context
from core.models.storage_entry import StorageEntry
from core.types import JsonValue

logger = get_logger(__name__)

_TABLE = "storage"
ContextGetter = Callable[[], Context | None]


def _encode_storage_value(value: JsonValue) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _storage_alias(db_url: str | None) -> str:
    database = get_settings().database
    if db_url is None or db_url == "":
        return "default"
    tracing_url = database.tracing_url
    if tracing_url is not None and tracing_url != "" and db_url == tracing_url:
        return "tracing"
    shared_url = database.shared_url
    if shared_url is not None and shared_url != "" and db_url == shared_url:
        return "shared"
    return "default"


def _require_storage_table(table_name: str) -> None:
    if table_name != _TABLE:
        raise ValueError(f"storage table is '{_TABLE}', got {table_name}")


def _expired(expired_at: datetime | None) -> bool:
    if expired_at is None:
        return False
    # Колонка timestamp without time zone: драйвер отдаёт UTC без tzinfo.
    if expired_at.tzinfo is None:
        expired_at = expired_at.replace(tzinfo=timezone.utc)
    return expired_at <= datetime.now(timezone.utc)


def _ttl_deadline(key: str, ttl: int | None) -> datetime | None:
    if ttl is not None:
        return datetime.now(timezone.utc) + timedelta(seconds=ttl)
    if key.startswith(("company:", "subdomain:", "token:")):
        return None
    return datetime.now(timezone.utc) + timedelta(days=5)


class Storage:
    """Доступ к таблице ``storage``."""

    def __init__(
        self,
        db_url: str | None = None,
        get_context_func: ContextGetter | None = None,
    ):
        self.db_url: str | None = db_url
        self.get_context_func: ContextGetter | None = get_context_func
        self._alias: str = _storage_alias(db_url)

    def _company_key(self, key: str, force_global: bool = False) -> str:
        if force_global:
            return key
        if key.startswith(
            (
                "company:",
                "subdomain:",
                "web_notification:",
                "media_group:",
                # Устройства и pairing ищутся по глобальному id до компании в контексте.
                # company_id лежит в записи, а не в префиксе ключа.
                "agent_pairing:",
                "agent_device:",
                "agent_tunnel_online:",
                "agent_token_deny:",
                "agent_token_jti_deny:",
                # Маркер сида и дедуп email-триггера: company_id уже внутри ключа.
                "flows:",
                # Дедуп уведомлений и индекс вложений: компания и ящик уже внутри ключа.
                "mail:notify:",
                "mail_attachment:",
                "calendar:notify:",
                # Прайс и settlement: глобальный каталог или company_id уже в ключе.
                "billing:",
                # Платёж и webhook: company_id или id операции провайдера уже в ключе.
                "payment:",
                "payment_external:",
                "payment_notification:",
                # OAuth callback и внешний автор: токен или company_id уже в ключе.
                "integration_oauth_state:",
                "integration_ext_author:",
            )
        ):
            return key
        if self.get_context_func is not None:
            context = self.get_context_func()
            if context is not None and context.active_company is not None:
                company_id = context.active_company.company_id
                if company_id == "":
                    raise ValueError("company_id is required")
                return f"company:{company_id}:{key}"
        return key

    async def get(
        self,
        key: str,
        force_global: bool = False,
        for_update: bool = False,
    ) -> str | None:
        final_key = self._company_key(key, force_global)
        memo = lookup_memoized(_TABLE, final_key, for_update=for_update)
        if memo.hit:
            return memo.value
        row = await StorageEntry.row(final_key, alias=self._alias, for_update=for_update)
        if row is None or _expired(row.expired_at):
            return None
        resolved = _encode_storage_value(row.value)
        if not for_update:
            set_memoized(_TABLE, final_key, resolved)
        return resolved

    async def insert_once(
        self,
        key: str,
        value: str,
        ttl: int | None = None,
        force_global: bool = False,
    ) -> bool:
        final_key = self._company_key(key, force_global)
        expired_at = None
        if ttl is not None:
            expired_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        return await StorageEntry.insert_once(
            final_key,
            value,
            expired_at,
            alias=self._alias,
        )

    async def set(
        self,
        key: str,
        value: str,
        ttl: int | None = None,
        force_global: bool = False,
    ) -> bool:
        final_key = self._company_key(key, force_global)
        await StorageEntry.upsert_by_key(
            final_key,
            value,
            _ttl_deadline(final_key, ttl),
            alias=self._alias,
        )
        invalidate_key(_TABLE, final_key)
        return True

    async def delete(self, key: str, force_global: bool = False) -> bool:
        final_key = self._company_key(key, force_global)
        deleted = await StorageEntry.delete_key(final_key, alias=self._alias)
        invalidate_key(_TABLE, final_key)
        if deleted:
            logger.debug("db.storage.deleted", key=final_key)
        return deleted > 0

    async def list_by_prefix(
        self, prefix: str, limit: int = 100, force_global: bool = False
    ) -> list[str]:
        final_prefix = self._company_key(prefix, force_global)
        rows = await StorageEntry.by_key_prefix(
            final_prefix,
            alias=self._alias,
            limit=limit,
        )
        return [row.key for row in rows]

    async def get_all_by_prefix(
        self, prefix: str, limit: int = 1000, force_global: bool = False
    ) -> dict[str, str]:
        final_prefix = self._company_key(prefix, force_global)
        rows = await StorageEntry.by_key_prefix(
            final_prefix,
            alias=self._alias,
            limit=limit,
        )
        return {row.key: _encode_storage_value(row.value) for row in rows}

    async def list_by_prefix_json_text_equals(
        self,
        prefix: str,
        *,
        field: str,
        equals: str,
        limit: int,
        newest_first: bool,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        force_global: bool = False,
    ) -> list[str]:
        if prefix.strip() == "":
            raise ValueError("prefix is required")
        if field.strip() == "":
            raise ValueError("field is required")
        if equals.strip() == "":
            raise ValueError("equals is required")
        if limit < 1:
            raise ValueError("limit must be >= 1")
        final_prefix = self._company_key(prefix, force_global)
        return await StorageEntry.list_by_prefix_json_text_equals(
            final_prefix,
            field=field,
            equals=equals,
            limit=limit,
            newest_first=newest_first,
            alias=self._alias,
            created_after=created_after,
            created_before=created_before,
        )

    async def get_many(self, keys: list[str], force_global: bool = False) -> dict[str, str]:
        if len(keys) == 0:
            return {}
        final_keys = [self._company_key(key, force_global) for key in keys]
        original_by_final = dict(zip(final_keys, keys, strict=True))
        rows = await StorageEntry.by_keys(final_keys, alias=self._alias)
        return {
            original_by_final[row.key]: _encode_storage_value(row.value)
            for row in rows
        }

    async def get_with_session_and_table(self, key: str, table_name: str) -> str | None:
        _require_storage_table(table_name)
        row = await StorageEntry.row(key, alias=self._alias, for_update=False)
        if row is None or _expired(row.expired_at):
            return None
        return _encode_storage_value(row.value)

    async def set_with_table(
        self, key: str, value: str, table_name: str, ttl: int | None = None
    ) -> bool:
        _require_storage_table(table_name)
        await StorageEntry.upsert_by_key(
            key,
            value,
            _ttl_deadline(key, ttl),
            alias=self._alias,
        )
        invalidate_key(_TABLE, key)
        return True

    async def delete_with_table(self, key: str, table_name: str) -> bool:
        _require_storage_table(table_name)
        deleted = await StorageEntry.delete_key(key, alias=self._alias)
        invalidate_key(_TABLE, key)
        return deleted

    async def get_all_by_prefix_and_table(
        self, prefix: str, table_name: str, limit: int = 1000, offset: int = 0
    ) -> dict[str, str]:
        _require_storage_table(table_name)
        if offset < 0:
            raise ValueError("offset must be >= 0")
        rows = await StorageEntry.by_key_prefix_updated(
            prefix,
            alias=self._alias,
            limit=limit,
            offset=offset,
        )
        return {row.key: _encode_storage_value(row.value) for row in rows}

    async def count_by_prefix_and_table(self, prefix: str, table_name: str) -> int:
        _require_storage_table(table_name)
        return await StorageEntry.count_by_key_prefix(prefix, alias=self._alias)

    async def get_many_with_table(self, keys: list[str], table_name: str) -> dict[str, str]:
        _require_storage_table(table_name)
        if len(keys) == 0:
            return {}
        rows = await StorageEntry.by_keys(keys, alias=self._alias)
        return {row.key: _encode_storage_value(row.value) for row in rows}


SharedStorage = NewType("SharedStorage", Storage)

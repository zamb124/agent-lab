"""
Хранилище снимков состояния сессии (cookies, storage_state, sessionStorage) в Redis.

Состояние сессии переживает рестарт пода и доступно между процессами: оно лежит в
Redis с TTL по ключу `browser:session_state:<state_key>`. Это позволяет warm/restore
сценариям (повторное открытие контекста с теми же cookies/storage) работать durable,
а не теряться вместе с памятью процесса.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Mapping
from dataclasses import asdict
from typing import cast
from urllib.parse import urlparse

from apps.browser.engine.types import (
    BrowserContextHandle,
    BrowserPage,
    BrowserStorageState,
    ContextSignature,
    PageMode,
    SessionStateBlob,
)
from core.clients.redis_client import RedisClient, RedisOperationError

_KEY_PREFIX = "browser:session_state:"


class SessionStateStore:
    """
    Redis-хранилище `SessionStateBlob` по ключу.

    Связи:
    - Используется interactor-ом в `save_state/restore_state` и при acquire с restore.
    - Сериализует/десериализует `SessionStateBlob` в JSON.

    Инварианты:
    - Доступ к отсутствующему ключу приводит к `KeyError`.
    - Неуспешная запись в Redis приводит к `RedisOperationError` (без тихой потери состояния).
    - `capture_from` сохраняет state в формате, пригодном для повторного `new_context`.
    """

    def __init__(self, *, redis_client: RedisClient, ttl_sec: int) -> None:
        if ttl_sec <= 0:
            raise ValueError("ttl_sec должен быть положительным")
        self._redis: RedisClient = redis_client
        self._ttl_sec: int = ttl_sec

    @staticmethod
    def _new_key() -> str:
        return secrets.token_hex(16)

    @staticmethod
    def _redis_key(state_key: str) -> str:
        if not state_key:
            raise ValueError("state_key обязателен")
        return f"{_KEY_PREFIX}{state_key}"

    @staticmethod
    def _serialize(blob: SessionStateBlob) -> str:
        return json.dumps(asdict(blob), ensure_ascii=False)

    @staticmethod
    def _deserialize(raw: str) -> SessionStateBlob:
        data = cast(Mapping[str, object], json.loads(raw))
        return SessionStateBlob(
            shared_storage_key=cast(str, data["shared_storage_key"]),
            storage_state=cast(BrowserStorageState, data["storage_state"]),
            session_storage_by_origin=cast(dict[str, dict[str, str]], data["session_storage_by_origin"]),
            current_url=cast(str, data["current_url"]),
            proxy_policy=cast(str, data["proxy_policy"]),
            anti_bot_tier=cast(str, data["anti_bot_tier"]),
            locale=cast(str, data["locale"]),
            timezone_id=cast(str, data["timezone_id"]),
            user_agent=cast("str | None", data["user_agent"]),
            page_mode=cast(PageMode, data["page_mode"]),
            permissions_fingerprint=cast(str, data["permissions_fingerprint"]),
            last_snapshot_ref=cast("str | None", data["last_snapshot_ref"]),
            pause_ttl_soft_sec=cast("int | None", data["pause_ttl_soft_sec"]),
            pause_ttl_hard_sec=cast("int | None", data["pause_ttl_hard_sec"]),
        )

    async def put(self, blob: SessionStateBlob) -> str:
        key = self._new_key()
        ok = await self._redis.set(self._redis_key(key), self._serialize(blob), ttl=self._ttl_sec)
        if not ok:
            raise RedisOperationError(f"put({key}): Redis недоступен, состояние сессии не сохранено")
        return key

    async def get(self, state_key: str) -> SessionStateBlob:
        raw = await self._redis.get(self._redis_key(state_key))
        if raw is None:
            raise KeyError(f"Неизвестный state_key: {state_key}")
        return self._deserialize(raw)

    async def delete(self, state_key: str) -> None:
        _ = await self._redis.delete(self._redis_key(state_key))

    async def capture_from(
        self,
        context: BrowserContextHandle,
        page: BrowserPage,
        *,
        shared_storage_key: str,
        context_signature: ContextSignature,
        last_snapshot_ref: str | None,
    ) -> str:
        current_url = page.url
        if current_url.startswith("about:"):
            raise ValueError("Нельзя сохранить состояние: current_url должен быть реальным URL, не about:*")
        _ = origin_from_url(current_url)
        storage_state = await context.storage_state()
        origin = origin_from_url(current_url)
        raw_session_storage = cast(
            object,
            await page.evaluate(
                """() => {
                const out = {};
                for (let i = 0; i < sessionStorage.length; i++) {
                    const k = sessionStorage.key(i);
                    if (k !== null) {
                        const v = sessionStorage.getItem(k);
                        if (v !== null) out[k] = v;
                    }
                }
                return out;
            }"""
            ),
        )
        if not isinstance(raw_session_storage, dict):
            raise ValueError("sessionStorage dump должен быть JSON object")
        raw_session_storage_map = cast(Mapping[object, object], raw_session_storage)
        session_storage_dump: dict[str, str] = {}
        for key, value in raw_session_storage_map.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError("sessionStorage dump должен содержать только string -> string")
            session_storage_dump[key] = value
        by_origin: dict[str, dict[str, str]] = {origin: dict(session_storage_dump)}
        blob = SessionStateBlob(
            shared_storage_key=shared_storage_key,
            storage_state=storage_state,
            session_storage_by_origin=by_origin,
            current_url=current_url,
            proxy_policy=context_signature.proxy_policy,
            anti_bot_tier=context_signature.anti_bot_tier,
            locale=context_signature.locale,
            timezone_id=context_signature.timezone_id,
            user_agent=context_signature.user_agent,
            page_mode=context_signature.page_mode,
            permissions_fingerprint=context_signature.permissions_fingerprint,
            last_snapshot_ref=last_snapshot_ref,
        )
        return await self.put(blob)

    async def storage_state_for_new_context(self, state_key: str) -> BrowserStorageState:
        blob = await self.get(state_key)
        return blob.storage_state

    async def session_storage_for_origin(self, state_key: str, origin: str) -> dict[str, str]:
        blob = await self.get(state_key)
        entries = blob.session_storage_by_origin.get(origin)
        if entries is None:
            return {}
        return dict(entries)

    async def current_url(self, state_key: str) -> str:
        blob = await self.get(state_key)
        if not blob.current_url:
            raise RuntimeError("SessionStateBlob.current_url должен быть непустой строкой")
        return blob.current_url


def origin_from_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Некорректный URL для origin: {url}")
    return f"{parsed.scheme}://{parsed.netloc}"

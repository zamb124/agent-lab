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
from dataclasses import asdict
from urllib.parse import urlparse

from pydantic import TypeAdapter, ValidationError

from apps.browser.models.types import (
    BrowserContextHandle,
    BrowserPage,
    BrowserStorageState,
    ContextSignature,
    PageMode,
    SessionStateBlob,
)
from apps.browser.services.page_evaluate import evaluate_json_value
from core.clients.redis_client import RedisClient, RedisOperationError
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object

_STORAGE_STATE_ADAPTER: TypeAdapter[BrowserStorageState] = TypeAdapter(BrowserStorageState)

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
            raise ValueError("ttl_sec must be positive")
        self._redis: RedisClient = redis_client
        self._ttl_sec: int = ttl_sec

    @staticmethod
    def _new_key() -> str:
        return secrets.token_hex(16)

    @staticmethod
    def _redis_key(state_key: str) -> str:
        if not state_key:
            raise ValueError("state_key is required")
        return f"{_KEY_PREFIX}{state_key}"

    @staticmethod
    def _serialize(blob: SessionStateBlob) -> str:
        return json.dumps(asdict(blob), ensure_ascii=False)

    @staticmethod
    def _deserialize(raw: str) -> SessionStateBlob:
        data = parse_json_object(raw, "session state")
        return SessionStateBlob(
            shared_storage_key=_require_str(data, "shared_storage_key"),
            storage_state=_storage_state(data["storage_state"]),
            session_storage_by_origin=_session_storage_by_origin(data["session_storage_by_origin"]),
            current_url=_require_str(data, "current_url"),
            proxy_policy=_require_str(data, "proxy_policy"),
            anti_bot_tier=_require_str(data, "anti_bot_tier"),
            locale=_require_str(data, "locale"),
            timezone_id=_require_str(data, "timezone_id"),
            user_agent=_optional_str(data, "user_agent"),
            page_mode=_page_mode(data["page_mode"]),
            permissions_fingerprint=_require_str(data, "permissions_fingerprint"),
            last_snapshot_ref=_optional_str(data, "last_snapshot_ref"),
            pause_ttl_soft_sec=_optional_int(data, "pause_ttl_soft_sec"),
            pause_ttl_hard_sec=_optional_int(data, "pause_ttl_hard_sec"),
        )

    async def put(self, blob: SessionStateBlob) -> str:
        key = self._new_key()
        ok = await self._redis.set(self._redis_key(key), self._serialize(blob), ttl=self._ttl_sec)
        if not ok:
            raise RedisOperationError(f"put({key}): Redis is unavailable, session state was not saved")
        return key

    async def get(self, state_key: str) -> SessionStateBlob:
        raw = await self._redis.get(self._redis_key(state_key))
        if raw is None:
            raise KeyError(f"Unknown state_key: {state_key}")
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
            raise ValueError("Cannot save state: current_url must be a real URL, not about:*")
        _ = origin_from_url(current_url)
        storage_state = await context.storage_state()
        origin = origin_from_url(current_url)
        dumped = require_json_object(
            await evaluate_json_value(
                page,
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
            }""",
                "sessionStorage",
            ),
            "sessionStorage",
        )
        session_storage_dump: dict[str, str] = {}
        for key, value in dumped.items():
            if not isinstance(value, str):
                raise ValueError("sessionStorage dump must contain only string -> string")
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
            raise RuntimeError("SessionStateBlob.current_url must be a non-empty string")
        return blob.current_url


def _require_str(data: JsonObject, field_name: str) -> str:
    value = data[field_name]
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


def _optional_str(data: JsonObject, field_name: str) -> str | None:
    value = data[field_name]
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string or null")
    return value


def _optional_int(data: JsonObject, field_name: str) -> int | None:
    value = data[field_name]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an int or null")
    return value


def _page_mode(value: JsonValue) -> PageMode:
    if value == "interactive":
        return "interactive"
    if value == "crawl":
        return "crawl"
    if value == "lite":
        return "lite"
    raise ValueError(f"page_mode is invalid: {value!r}")


def _storage_state(value: JsonValue) -> BrowserStorageState:
    try:
        return _STORAGE_STATE_ADAPTER.validate_python(value)
    except ValidationError as exc:
        raise ValueError("storage_state must be a Playwright storage state") from exc


def _session_storage_by_origin(value: JsonValue) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict):
        raise ValueError("session_storage_by_origin must be a JSON object")
    by_origin: dict[str, dict[str, str]] = {}
    for origin, entries in value.items():
        if not isinstance(entries, dict):
            raise ValueError("session_storage_by_origin values must be JSON objects")
        bucket: dict[str, str] = {}
        for key, item in entries.items():
            if not isinstance(item, str):
                raise ValueError("sessionStorage values must be strings")
            bucket[key] = item
        by_origin[origin] = bucket
    return by_origin


def origin_from_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid URL for origin: {url}")
    return f"{parsed.scheme}://{parsed.netloc}"

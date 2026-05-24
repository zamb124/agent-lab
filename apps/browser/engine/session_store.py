"""
Хранилище снимков состояния сессии (cookies, storage_state, sessionStorage).
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from typing import cast
from urllib.parse import urlparse

from apps.browser.engine.types import (
    BrowserContextHandle,
    BrowserPage,
    BrowserStorageState,
    ContextSignature,
    SessionStateBlob,
)


class SessionStateStore:
    """
    In-memory хранилище state blob по ключу (v1).

    Мотивация:
    - Нужен простой и быстрый слой для warm/restore без внешней БД.
    - Сессия должна уметь переносить cookies/storage между запусками контекста.

    Связи:
    - Используется interactor-ом в `save_state/restore_state`.
    - Сохраняет/выдаёт объекты `SessionStateBlob`.

    Состояние:
    - `_blobs`: map `state_key -> SessionStateBlob`.

    Инварианты:
    - Доступ к отсутствующему ключу приводит к `KeyError`.
    - `capture_from` сохраняет state в формате, пригодном для повторного `new_context`.

    Переиспользование:
    - Стоит: для in-process runtime и тестовых/локальных сценариев.
    - Не стоит: для распределённого кластера между процессами; там нужен внешний store
      (например Redis/Postgres) с тем же контрактом ключ->blob.
    """

    def __init__(self) -> None:
        self._blobs: dict[str, SessionStateBlob] = {}

    def _new_key(self) -> str:
        return secrets.token_hex(16)

    def put(self, blob: SessionStateBlob) -> str:
        key = self._new_key()
        self._blobs[key] = blob
        return key

    def get(self, state_key: str) -> SessionStateBlob:
        if state_key not in self._blobs:
            raise KeyError(f"Неизвестный state_key: {state_key}")
        return self._blobs[state_key]

    def delete(self, state_key: str) -> None:
        _ = self._blobs.pop(state_key, None)

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
        return self.put(blob)

    def storage_state_for_new_context(self, state_key: str) -> BrowserStorageState:
        blob = self.get(state_key)
        return blob.storage_state

    def session_storage_for_origin(self, state_key: str, origin: str) -> dict[str, str]:
        blob = self.get(state_key)
        entries = blob.session_storage_by_origin.get(origin)
        if entries is None:
            return {}
        return dict(entries)

    def current_url(self, state_key: str) -> str:
        blob = self.get(state_key)
        if not blob.current_url:
            raise RuntimeError("SessionStateBlob.current_url должен быть непустой строкой")
        return blob.current_url

    def context_signature_for_restore(self, state_key: str) -> ContextSignature:
        blob = self.get(state_key)
        if blob.pause_ttl_hard_sec is not None or blob.pause_ttl_soft_sec is not None:
            soft = blob.pause_ttl_soft_sec
            hard = blob.pause_ttl_hard_sec
            if soft is None or hard is None:
                raise ValueError("pause_ttl_soft_sec и pause_ttl_hard_sec должны быть заданы вместе")
            if soft <= 0 or hard <= 0:
                raise ValueError("pause_ttl_soft_sec и pause_ttl_hard_sec должны быть int > 0")
            if soft > hard:
                raise ValueError("pause_ttl_soft_sec должен быть <= pause_ttl_hard_sec")
        return ContextSignature(
            proxy_policy=blob.proxy_policy,
            shared_storage_key=blob.shared_storage_key,
            anti_bot_tier=blob.anti_bot_tier,
            stealth_init_version="v1",
            locale=blob.locale,
            timezone_id=blob.timezone_id,
            user_agent=blob.user_agent,
            page_mode=blob.page_mode,
            permissions_fingerprint=blob.permissions_fingerprint,
        )


def origin_from_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Некорректный URL для origin: {url}")
    return f"{parsed.scheme}://{parsed.netloc}"

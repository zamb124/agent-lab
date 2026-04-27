"""
Хранилище снимков состояния сессии (cookies, storage_state, sessionStorage).
"""

from __future__ import annotations

import secrets
from typing import Any, Optional
from urllib.parse import urlparse

from apps.browser.engine.types import SessionStateBlob


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
        self._blobs.pop(state_key, None)

    async def capture_from(
        self,
        context: Any,
        page: Any,
        *,
        shared_storage_key: str,
        last_snapshot_ref: Optional[str],
    ) -> str:
        storage_state = await context.storage_state()
        origin = origin_from_url(page.url)
        session_storage_dump: dict[str, str] = await page.evaluate(
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
        )
        by_origin: dict[str, dict[str, str]] = {origin: session_storage_dump}
        blob = SessionStateBlob(
            shared_storage_key=shared_storage_key,
            storage_state=storage_state,
            session_storage_by_origin=by_origin,
            last_snapshot_ref=last_snapshot_ref,
        )
        return self.put(blob)

    def storage_state_for_new_context(self, state_key: str) -> dict[str, Any]:
        blob = self.get(state_key)
        return blob.storage_state

    def session_storage_for_origin(self, state_key: str, origin: str) -> dict[str, str]:
        blob = self.get(state_key)
        if origin not in blob.session_storage_by_origin:
            return {}
        return dict(blob.session_storage_by_origin[origin])


def origin_from_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Некорректный URL для origin: {url}")
    return f"{parsed.scheme}://{parsed.netloc}"

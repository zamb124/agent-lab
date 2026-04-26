"""
Учёт аренды страниц: session_id, TTL, блокировка гонок, kill_session.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Optional

from apps.browser.runtime.context_factory import ContextFactory
from apps.browser.runtime.types import ContextSignature, SessionMode


@dataclass
class LeaseRecord:
    """
    Запись об активной аренде страницы.

    Мотивация:
    - Нужна единая структура, чтобы управлять TTL, release и привязкой к session_id
      без обхода внутренних структур runtime.

    Переиспользование:
    - Стоит: как внутренний runtime-record для трекинга активных lease.
    - Не стоит: как внешний API-контракт.

    Связи:
    - Хранится в `PageLeaseManager._leases`.
    - Используется для release/TTL sweep/kill_session.

    Состояние:
    - Идентификаторы сессии и endpoint-а, сигнатура контекста, ссылка на page.
    - Момент acquire и TTL, режим жизненного цикла (`warm`/`restore`).

    Инварианты:
    - Запись существует только пока страница находится в активном lease.
    """
    session_id: str
    endpoint_key: str
    context_signature: ContextSignature
    page: Any
    acquired_monotonic: float
    ttl_sec: int
    session_mode: SessionMode


@dataclass
class SessionContextRecord:
    """
    Запись о контексте, закреплённом за бизнес-сессией.

    Инвариант:
    - Ровно один `BrowserContext` на один `session_id`.
    """
    session_id: str
    endpoint_key: str
    context_signature: ContextSignature
    context: Any
    idle_deadline_monotonic: Optional[float]
    session_mode: SessionMode


class PageLeaseManager:
    """
    Учёт активных page lease и связь `session_id -> page`.

    Мотивация:
    - Разделить concerns: `ContextFactory` управляет контекстами, а этот класс —
      логическими арендами страниц и правилами session-level доступа.
    - Дать deterministic поведение control API: одна сессия -> одна выбранная page.

    Связи:
    - Делегирует фактическое создание/закрытие страниц в `ContextFactory`.
    - Используется interactor-ом, lifecycle-менеджером и HTTP API.

    Модель изоляции и очистки (важно):
    - Контекст привязан к бизнес-сессии: один `session_id` -> один `BrowserContext`.
      Переиспользование контекста между разными сессиями отключено.
    - TTL относится к *lease страницы* и считается от момента `lease_page()`
      (поле `LeaseRecord.acquired_monotonic`). В этой модели нет heartbeats/touch:
      использование страницы не продлевает lease.
    - `sweep_expired()` освобождает (close) страницы, чей lease истёк.
    - `BrowserContext` закрывается, когда у сессии нет активных страниц и:
      - `session_mode == "restore"` — сразу,
      - `session_mode == "warm"` — по истечении `warm_idle_sec` (idle TTL для контекста).
    - Если потребуется оптимизация старта, можно рассмотреть отдельный слой реюза
      `BrowserContext` (по сигнатуре) с явными инвариантами изоляции и eviction.

    Состояние:
    - `_leases`: map `id(page) -> LeaseRecord`.
    - `_session_pages`: map `session_id -> set[id(page)]`.
    - `_allow_acquire`: глобальный флаг запрета новых выдач (на случай полного shutdown/drain).
    - `_draining_endpoints`: endpoint-ы, где временно запрещены новые lease.
    - `_session_contexts`: активные BrowserContext по session_id.

    Инварианты:
    - Освобождение неизвестной страницы считается ошибкой.
    - Для control API `get_page_for_session` не делает неявный выбор между несколькими страницами.
    - Во время endpoint-drain новые lease запрещены только для выбранного endpoint-а.

    Важно про ограничение control API:
    - Ограничение "одна активная страница" относится к одному `session_id`.
    - Это не ограничение по URL: разные `session_id` могут одновременно держать страницы
      на одном и том же URL без конфликта.

    Переиспользование:
    - Стоит: в любом сценарии, где есть несколько параллельных сессий и нужен
      контроль TTL/drain/kill_session.
    - Не стоит: в одноразовых скриптах без сессионного API, где lifecycle страницы
      полностью локален и не требует общего учёта.
    """
    def __init__(self, context_factory: ContextFactory) -> None:
        self._factory = context_factory
        self._lock = asyncio.Lock()
        self._leases: dict[int, LeaseRecord] = {}
        self._session_pages: dict[str, set[int]] = {}
        self._allow_acquire = True
        self._draining_endpoints: set[str] = set()
        self._session_contexts: dict[str, SessionContextRecord] = {}

    def set_allow_acquire(self, value: bool) -> None:
        self._allow_acquire = value

    @property
    def allow_acquire(self) -> bool:
        return self._allow_acquire

    def set_endpoint_drain(self, endpoint_key: str, value: bool) -> None:
        if not endpoint_key:
            raise ValueError("endpoint_key обязателен")
        if value:
            self._draining_endpoints.add(endpoint_key)
            return
        self._draining_endpoints.discard(endpoint_key)

    def endpoint_is_draining(self, endpoint_key: str) -> bool:
        return endpoint_key in self._draining_endpoints

    async def lease_page(
        self,
        browser: Any,
        endpoint_key: str,
        signature: ContextSignature,
        session_id: str,
        *,
        storage_state: Optional[dict[str, Any]],
        session_mode: SessionMode,
        page_ttl_sec: int,
        warm_idle_sec: int,
    ) -> tuple[Any, Any, bool]:
        if not self._allow_acquire:
            raise RuntimeError("Новые lease запрещены (drain)")
        if endpoint_key in self._draining_endpoints:
            raise RuntimeError(f"Новые lease запрещены для endpoint={endpoint_key} (drain)")
        await self._release_expired_leases(
            warm_idle_sec=warm_idle_sec,
        )
        await self._evict_idle_contexts()
        async with self._lock:
            ctx_rec = self._session_contexts.get(session_id)
        cold_start = ctx_rec is None
        if ctx_rec is None:
            context = await self._factory.new_context(
                browser,
                signature,
                storage_state,
            )
            ctx_rec = SessionContextRecord(
                session_id=session_id,
                endpoint_key=endpoint_key,
                context_signature=signature,
                context=context,
                idle_deadline_monotonic=None,
                session_mode=session_mode,
            )
            async with self._lock:
                self._session_contexts[session_id] = ctx_rec
        else:
            if ctx_rec.endpoint_key != endpoint_key:
                raise RuntimeError(
                    f"Сессия привязана к другому endpoint: session_id={session_id} "
                    f"endpoint={ctx_rec.endpoint_key} (запрошен {endpoint_key})"
                )
            if ctx_rec.context_signature.stable_hash() != signature.stable_hash():
                raise RuntimeError(
                    f"Сессия привязана к другой сигнатуре контекста: session_id={session_id} "
                    f"signature_hash={ctx_rec.context_signature.stable_hash()} (запрошен {signature.stable_hash()})"
                )
            ctx_rec.idle_deadline_monotonic = None
            ctx_rec.session_mode = session_mode
            context = ctx_rec.context

        page = await self._factory.new_page(context)
        rec = LeaseRecord(
            session_id=session_id,
            endpoint_key=endpoint_key,
            context_signature=signature,
            page=page,
            acquired_monotonic=time.monotonic(),
            ttl_sec=page_ttl_sec,
            session_mode=session_mode,
        )
        pid = id(page)
        async with self._lock:
            self._leases[pid] = rec
            self._session_pages.setdefault(session_id, set()).add(pid)
        return context, page, cold_start

    async def release_page(
        self,
        page: Any,
        *,
        warm_idle_sec: int,
        session_mode_override: Optional[SessionMode] = None,
    ) -> None:
        pid = id(page)
        ctx_to_close: Any | None = None
        async with self._lock:
            rec = self._leases.pop(pid, None)
            if rec is None:
                raise RuntimeError("Страница не зарегистрирована в менеджере аренды")
            sess = self._session_pages.get(rec.session_id)
            if sess is not None:
                sess.discard(pid)
                if len(sess) == 0:
                    self._session_pages.pop(rec.session_id, None)
            session_mode = session_mode_override if session_mode_override is not None else rec.session_mode
            ctx_rec = self._session_contexts.get(rec.session_id)
            if ctx_rec is not None and (sess is None or len(sess) == 0):
                if session_mode == "warm" and warm_idle_sec > 0:
                    ctx_rec.idle_deadline_monotonic = time.monotonic() + warm_idle_sec
                else:
                    ctx_to_close = ctx_rec.context
                    self._session_contexts.pop(rec.session_id, None)
        await self._factory.close_page(page)
        if ctx_to_close is not None:
            await self._factory.close_context(ctx_to_close)

    async def sweep_expired(self, *, warm_idle_sec: int) -> None:
        await self._release_expired_leases(
            warm_idle_sec=warm_idle_sec,
        )

    async def _release_expired_leases(
        self,
        *,
        warm_idle_sec: int,
    ) -> None:
        now = time.monotonic()
        async with self._lock:
            expired = [
                rec
                for rec in list(self._leases.values())
                if now - rec.acquired_monotonic > rec.ttl_sec
            ]
        for rec in expired:
            await self.release_page(
                rec.page,
                warm_idle_sec=warm_idle_sec,
                session_mode_override="restore",
            )

    async def kill_session(self, session_id: str, *, warm_idle_sec: int) -> None:
        async with self._lock:
            pids = list(self._session_pages.get(session_id, set()))
            recs = [self._leases[pid] for pid in pids if pid in self._leases]
        for rec in recs:
            await self.release_page(
                rec.page,
                warm_idle_sec=warm_idle_sec,
                session_mode_override="restore",
            )
        async with self._lock:
            ctx_rec = self._session_contexts.pop(session_id, None)
        if ctx_rec is not None:
            await self._factory.close_context(ctx_rec.context)

    async def close_all(self) -> None:
        """
        Закрыть все активные страницы и контексты.

        Используется при остановке runtime процесса.
        """
        async with self._lock:
            session_ids = list(self._session_contexts.keys())
        for sid in session_ids:
            await self.kill_session(sid, warm_idle_sec=0)

    async def kill_endpoint(self, endpoint_key: str) -> None:
        """
        Принудительно закрыть все страницы/контексты для endpoint.

        Используется для lifecycle disconnect/terminate: сначала закрываем всё, затем
        отключаем транспорт/браузер на уровне `CDPConnectionPool`.
        """
        async with self._lock:
            recs = [rec for rec in self._leases.values() if rec.endpoint_key == endpoint_key]
            session_ids = [sid for sid, ctx in self._session_contexts.items() if ctx.endpoint_key == endpoint_key]
        for rec in recs:
            await self.release_page(rec.page, warm_idle_sec=0, session_mode_override="restore")
        for sid in session_ids:
            await self.kill_session(sid, warm_idle_sec=0)

    async def close_idle_contexts_for_endpoint(self, endpoint_key: str) -> None:
        """
        Закрыть idle-контексты endpoint-а (warm idle TTL истёк, активных страниц нет).
        """
        now = time.monotonic()
        async with self._lock:
            to_close = [
                (sid, ctx.context)
                for sid, ctx in self._session_contexts.items()
                if ctx.endpoint_key == endpoint_key
                and ctx.idle_deadline_monotonic is not None
                and ctx.idle_deadline_monotonic <= now
                and len(self._session_pages.get(sid, set())) == 0
            ]
            for sid, _ in to_close:
                self._session_contexts.pop(sid, None)
        for _, context in to_close:
            await self._factory.close_context(context)

    async def _evict_idle_contexts(self) -> None:
        now = time.monotonic()
        async with self._lock:
            to_close = [
                (sid, ctx.context)
                for sid, ctx in self._session_contexts.items()
                if ctx.idle_deadline_monotonic is not None
                and ctx.idle_deadline_monotonic <= now
                and len(self._session_pages.get(sid, set())) == 0
            ]
            for sid, _ in to_close:
                self._session_contexts.pop(sid, None)
        for _, context in to_close:
            await self._factory.close_context(context)

    def active_lease_count_for_endpoint(self, endpoint_key: str) -> int:
        return sum(1 for rec in self._leases.values() if rec.endpoint_key == endpoint_key)

    def total_active_leases(self) -> int:
        return len(self._leases)

    async def get_page_for_session(self, session_id: str) -> Any:
        """
        Одна активная страница на session_id для Browser Control HTTP API.
        При нуле или нескольких страницах — ошибка (zero-guess).
        """
        async with self._lock:
            pids = self._session_pages.get(session_id)
            if pids is None or len(pids) == 0:
                raise KeyError(f"Нет активной страницы для session_id={session_id}")
            if len(pids) > 1:
                raise RuntimeError(
                    f"Ожидалась одна страница на session_id={session_id}, "
                    f"активно {len(pids)} (control API не выбирает неявно)",
                )
            pid = next(iter(pids))
            rec = self._leases.get(pid)
            if rec is None:
                raise RuntimeError(f"Lease record отсутствует для page id={pid}")
            return rec.page

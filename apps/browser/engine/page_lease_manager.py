"""
Учёт аренды страниц: session_id, TTL, блокировка гонок, kill_session.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from playwright.async_api import (
    ConsoleMessage,
    Request,
    Response,
    SourceLocation,
)
from playwright.async_api import (
    Error as PlaywrightError,
)

from apps.browser.engine.context_factory import ContextFactory
from apps.browser.engine.types import (
    BrowserContextHandle,
    BrowserHandle,
    BrowserPage,
    BrowserStorageState,
    ContextSignature,
    SessionMode,
)
from core.types import JsonObject

ConsoleHandler = Callable[[ConsoleMessage], None]
PageErrorHandler = Callable[[PlaywrightError], None]
RequestHandler = Callable[[Request], None]
ResponseHandler = Callable[[Response], None]
PageEventListeners = tuple[ConsoleHandler, PageErrorHandler, RequestHandler, ResponseHandler]
PageEventLogger = Callable[[str, JsonObject], None]


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
    page: BrowserPage
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
    context: BrowserContextHandle
    idle_deadline_monotonic: float | None
    session_mode: SessionMode


@dataclass(frozen=True)
class HumanTakeoverRecord:
    """
    Маркер ручного управления browser-сессией.

    Пока запись активна, агентские control/MCP-команды не должны выполнять
    навигацию или семантические действия в этой сессии. Preview-канал при этом
    продолжает читать screenshot/status и отправлять raw pointer/keyboard input.
    """
    session_id: str
    owner: str
    started_monotonic: float


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
    def __init__(
        self,
        context_factory: ContextFactory,
        *,
        page_event_logger: PageEventLogger | None = None,
    ) -> None:
        self._factory: ContextFactory = context_factory
        self._lock: asyncio.Lock = asyncio.Lock()
        self._leases: dict[int, LeaseRecord] = {}
        self._session_pages: dict[str, set[int]] = {}
        self._allow_acquire: bool = True
        self._draining_endpoints: set[str] = set()
        self._session_contexts: dict[str, SessionContextRecord] = {}
        # События для дебага страницы: console/pageerror/network.
        # Пишутся в artifacts как sidecar и используются для triage.
        self._console_events_by_session: dict[str, list[JsonObject]] = {}
        self._console_listeners_by_page: dict[int, PageEventListeners] = {}
        self._page_event_logger: PageEventLogger | None = page_event_logger
        self._navigate_locks: dict[str, asyncio.Lock] = {}
        self._human_takeovers: dict[str, HumanTakeoverRecord] = {}

    @staticmethod
    def _console_location(msg: ConsoleMessage) -> JsonObject:
        """
        Нормализовать location console-msg, если движок поддерживает.
        """
        loc: SourceLocation = msg.location
        out: JsonObject = {}
        url = loc.get("url")
        line = loc.get("lineNumber")
        col = loc.get("columnNumber")
        if url:
            out["url"] = url
        if line >= 0:
            out["line"] = line
        if col >= 0:
            out["column"] = col
        return out

    def _append_console_event(self, session_id: str, event: JsonObject) -> None:
        if not session_id:
            raise ValueError("session_id обязателен")
        self._console_events_by_session.setdefault(session_id, []).append(event)
        if self._page_event_logger is not None:
            payload: JsonObject = dict(event)
            payload["ts_ms"] = int(time.time() * 1000)
            self._page_event_logger(session_id, payload)

    def _attach_console_listeners(self, *, session_id: str, page: BrowserPage) -> None:
        pid = id(page)
        if pid in self._console_listeners_by_page:
            raise RuntimeError("Console listeners уже зарегистрированы для страницы")

        def on_console(msg: ConsoleMessage) -> None:
            self._append_console_event(
                session_id,
                {
                    "kind": "console",
                    "type": msg.type,
                    "text": msg.text,
                    "location": self._console_location(msg),
                },
            )

        def on_page_error(err: PlaywrightError) -> None:
            message = err.message
            stack = err.stack or ""
            payload: JsonObject = {"kind": "pageerror", "message": message}
            if stack:
                payload["stack"] = stack
            self._append_console_event(session_id, payload)

        def on_request_failed(req: Request) -> None:
            failure = req.failure or ""
            self._append_console_event(
                session_id,
                {
                    "kind": "requestfailed",
                    "url": req.url,
                    "method": req.method,
                    "failure": failure,
                },
            )

        def on_response(resp: Response) -> None:
            status = resp.status
            if status < 400:
                return
            self._append_console_event(
                session_id,
                {
                    "kind": "http_error",
                    "url": resp.url,
                    "status": status,
                },
            )

        page.on("console", on_console)
        page.on("pageerror", on_page_error)
        page.on("requestfailed", on_request_failed)
        page.on("response", on_response)
        self._console_listeners_by_page[pid] = (on_console, on_page_error, on_request_failed, on_response)

    def _detach_console_listeners(self, page: BrowserPage) -> None:
        pid = id(page)
        listeners = self._console_listeners_by_page.pop(pid, None)
        if listeners is None:
            return
        on_console, on_page_error, on_request_failed, on_response = listeners
        page.remove_listener("console", on_console)
        page.remove_listener("pageerror", on_page_error)
        page.remove_listener("requestfailed", on_request_failed)
        page.remove_listener("response", on_response)

    @asynccontextmanager
    async def session_navigate_exclusive(self, session_id: str) -> AsyncGenerator[None, None]:
        """
        Сериализация navigate (и kill_session для того же session_id) на одной сессии.

        Назначение:
        - Исключить гонку двух navigate на одном session_id (общая страница до swap).
        - Согласовать kill_session с in-flight navigate.
        """
        if not session_id:
            raise ValueError("session_id обязателен")
        lock = self._navigate_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            yield

    async def begin_human_takeover(self, session_id: str, *, owner: str) -> HumanTakeoverRecord:
        if not session_id:
            raise ValueError("session_id обязателен")
        takeover_owner = owner.strip() if owner.strip() else "human"
        async with self._lock:
            pids = self._session_pages.get(session_id)
            if pids is None or len(pids) == 0:
                raise KeyError(f"Нет активной страницы для session_id={session_id}")
            record = HumanTakeoverRecord(
                session_id=session_id,
                owner=takeover_owner,
                started_monotonic=time.monotonic(),
            )
            self._human_takeovers[session_id] = record
            return record

    async def end_human_takeover(self, session_id: str) -> HumanTakeoverRecord | None:
        if not session_id:
            raise ValueError("session_id обязателен")
        async with self._lock:
            return self._human_takeovers.pop(session_id, None)

    async def human_takeover_for_session(self, session_id: str) -> HumanTakeoverRecord | None:
        if not session_id:
            raise ValueError("session_id обязателен")
        async with self._lock:
            return self._human_takeovers.get(session_id)

    async def swap_active_page_for_session(self, session_id: str) -> BrowserPage:
        """
        Закрыть текущую вкладку сессии, открыть новую в том же BrowserContext и вернуть page.

        Инвариант:
        - После успешного swap у session_id снова ровно одна активная страница в менеджере.
        """
        async with self._lock:
            ctx_rec = self._session_contexts.get(session_id)
            if ctx_rec is None:
                raise KeyError(f"Нет контекста для session_id={session_id}")
            pids = self._session_pages.get(session_id)
            if pids is None or len(pids) != 1:
                raise RuntimeError(
                    "swap_active_page_for_session: ожидалась ровно одна страница для "
                    + f"session_id={session_id}, активно {0 if pids is None else len(pids)}",
                )
            old_pid = next(iter(pids))
            old_rec = self._leases.pop(old_pid, None)
            if old_rec is None:
                raise RuntimeError("swap_active_page_for_session: lease record отсутствует")
            old_page = old_rec.page
            _ = self._session_pages.pop(session_id, None)

        self._detach_console_listeners(old_page)
        await self._factory.close_page(old_page)

        new_page = await self._factory.new_page(ctx_rec.context)
        self._attach_console_listeners(session_id=session_id, page=new_page)
        new_rec = LeaseRecord(
            session_id=session_id,
            endpoint_key=old_rec.endpoint_key,
            context_signature=old_rec.context_signature,
            page=new_page,
            acquired_monotonic=time.monotonic(),
            ttl_sec=old_rec.ttl_sec,
            session_mode=old_rec.session_mode,
        )
        new_pid = id(new_page)
        async with self._lock:
            current_ctx = self._session_contexts.get(session_id)
            if current_ctx is not ctx_rec:
                raise RuntimeError("swap_active_page_for_session: контекст сессии изменился во время swap")
            self._leases[new_pid] = new_rec
            self._session_pages[session_id] = {new_pid}
        return new_page

    def drain_console_events(self, session_id: str) -> list[JsonObject]:
        """
        Слить накопленные debug-события страницы для session_id и очистить буфер.

        События включают:
        - console
        - pageerror
        - requestfailed
        - http_error (status >= 400)
        """
        if not session_id:
            raise ValueError("session_id обязателен")
        events = self._console_events_by_session.get(session_id)
        if events is None or len(events) == 0:
            return []
        self._console_events_by_session[session_id] = []
        return events

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

    async def context_signature_for_context(
        self,
        context: BrowserContextHandle,
    ) -> ContextSignature:
        async with self._lock:
            for record in self._session_contexts.values():
                if record.context is context:
                    return record.context_signature
        raise RuntimeError("BrowserContext не зарегистрирован в PageLeaseManager")

    async def lease_page(
        self,
        browser: BrowserHandle,
        endpoint_key: str,
        signature: ContextSignature,
        session_id: str,
        *,
        storage_state: BrowserStorageState | None,
        session_mode: SessionMode,
        page_ttl_sec: int,
        warm_idle_sec: int,
    ) -> tuple[BrowserContextHandle, BrowserPage, bool]:
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
                endpoint_key,
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
                    + f"endpoint={ctx_rec.endpoint_key} (запрошен {endpoint_key})"
                )
            if ctx_rec.context_signature.stable_hash() != signature.stable_hash():
                raise RuntimeError(
                    f"Сессия привязана к другой сигнатуре контекста: session_id={session_id} "
                    + f"signature_hash={ctx_rec.context_signature.stable_hash()} (запрошен {signature.stable_hash()})"
                )
            ctx_rec.idle_deadline_monotonic = None
            ctx_rec.session_mode = session_mode
            context = ctx_rec.context

        page = await self._factory.new_page(context)
        self._attach_console_listeners(session_id=session_id, page=page)
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
        page: BrowserPage,
        *,
        warm_idle_sec: int,
        session_mode_override: SessionMode | None = None,
    ) -> None:
        pid = id(page)
        ctx_to_close: BrowserContextHandle | None = None
        async with self._lock:
            rec = self._leases.pop(pid, None)
            if rec is None:
                raise RuntimeError("Страница не зарегистрирована в менеджере аренды")
            sess = self._session_pages.get(rec.session_id)
            if sess is not None:
                sess.discard(pid)
                if len(sess) == 0:
                    _ = self._session_pages.pop(rec.session_id, None)
                    _ = self._human_takeovers.pop(rec.session_id, None)
            session_mode = session_mode_override if session_mode_override is not None else rec.session_mode
            ctx_rec = self._session_contexts.get(rec.session_id)
            if ctx_rec is not None and (sess is None or len(sess) == 0):
                if session_mode == "warm" and warm_idle_sec > 0:
                    ctx_rec.idle_deadline_monotonic = time.monotonic() + warm_idle_sec
                else:
                    ctx_to_close = ctx_rec.context
                    _ = self._session_contexts.pop(rec.session_id, None)
        self._detach_console_listeners(page)
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
        async with self.session_navigate_exclusive(session_id):
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
                _ = self._human_takeovers.pop(session_id, None)
            if ctx_rec is not None:
                await self._factory.close_context(ctx_rec.context)
            _ = self._console_events_by_session.pop(session_id, None)
        _ = self._navigate_locks.pop(session_id, None)

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
                _ = self._session_contexts.pop(sid, None)
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
                _ = self._session_contexts.pop(sid, None)
        for _, context in to_close:
            await self._factory.close_context(context)

    def active_lease_count_for_endpoint(self, endpoint_key: str) -> int:
        return sum(1 for rec in self._leases.values() if rec.endpoint_key == endpoint_key)

    def total_active_leases(self) -> int:
        return len(self._leases)

    async def get_page_for_session(self, session_id: str) -> BrowserPage:
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
                    + f"активно {len(pids)} (control API не выбирает неявно)",
                )
            pid = next(iter(pids))
            rec = self._leases.get(pid)
            if rec is None:
                raise RuntimeError(f"Lease record отсутствует для page id={pid}")
            return rec.page

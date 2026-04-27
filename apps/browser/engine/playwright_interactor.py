"""
Playwright-реализация BrowserInteractor (§17).
"""

from __future__ import annotations

import ast
import asyncio
import io
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Optional

from apps.browser.engine.cdp_pool import CDPConnectionPool
from apps.browser.engine.page_lease_manager import PageLeaseManager
from apps.browser.engine.session_store import SessionStateStore, origin_from_url
from apps.browser.engine.types import (
    SELECTOR_PREFIX,
    BrowserAcquireRequest,
    BrowserAcquireResult,
    BrowserFetchRequest,
    BrowserFetchResult,
    BrowserRuntimeSettingsView,
    ExecCodeResult,
)


class PlaywrightBrowserInteractor:
    """
    Реализация `BrowserInteractor` поверх Playwright + CDP.

    Мотивация:
    - Сконцентрировать все "браузерные действия" в одном слое: acquire/fetch/exec/state/release.
    - Спрятать детали Playwright от API и adapter-слоя, оставив стабильный контракт.

    Связи:
    - Получает Browser из `CDPConnectionPool`.
    - Делегирует выдачу/освобождение page в `PageLeaseManager`.
    - Сохраняет и восстанавливает состояние через `SessionStateStore`.

    Состояние:
    - Ссылки на pool/store/lease manager и runtime-настройки.

    Инварианты:
    - Acquire всегда использует валидный endpoint из настроек.
    - `fetch` принимает только поддержанные `wait_policy`.
    - `exec_code` работает в sandbox с запретом import.

    Что именно переиспользуется:
    - Browser transport переиспользуется через `CDPConnectionPool` (по endpoint).
    - BrowserContext закреплён за `session_id` через `PageLeaseManager` (одна сессия -> один контекст).
      Переиспользование контекста между разными сессиями отключено.
    - Page не переиспользуется автоматически: на каждый lease выдаётся новая вкладка в контексте сессии.

    Переиспользование:
    - Стоит: как default interactor для CDP-движков (Lightpanda/Chromium) и control API.
    - Не стоит: если нужен альтернативный движок/протокол; тогда лучше реализовать
      новый interactor под тот же `BrowserInteractor` контракт.
    """
    def __init__(
        self,
        *,
        pool: CDPConnectionPool,
        session_store: SessionStateStore,
        lease_manager: PageLeaseManager,
        settings: BrowserRuntimeSettingsView,
    ) -> None:
        self._pool = pool
        self._store = session_store
        self._leases = lease_manager
        self._settings = settings

    def _cdp_url(self, endpoint_key: str) -> str:
        urls = self._settings.cdp_urls_by_endpoint
        if endpoint_key not in urls:
            raise KeyError(f"Нет CDP URL для endpoint_key={endpoint_key}")
        url = urls[endpoint_key]
        if not url:
            raise ValueError(f"Пустой CDP URL для endpoint_key={endpoint_key}")
        return url

    @staticmethod
    def _proxy_id(proxy_policy: str) -> Optional[str]:
        if (
            proxy_policy.startswith("http://")
            or proxy_policy.startswith("https://")
            or proxy_policy.startswith("socks5://")
        ):
            return proxy_policy
        return None

    async def acquire(self, req: BrowserAcquireRequest) -> BrowserAcquireResult:
        await self._leases.sweep_expired(warm_idle_sec=self._settings.warm_idle_sec)
        cdp_url = self._cdp_url(req.endpoint_key)
        browser = await self._pool.acquire_browser(req.endpoint_key, cdp_url)
        storage_state: Optional[dict[str, Any]] = None
        if req.restore_state_key is not None:
            storage_state = self._store.storage_state_for_new_context(req.restore_state_key)
        _context, page, cold_start = await self._leases.lease_page(
            browser,
            req.endpoint_key,
            req.context_signature,
            req.session_id,
            storage_state=storage_state,
            session_mode=req.session_mode,
            page_ttl_sec=self._settings.default_page_ttl_sec,
            warm_idle_sec=self._settings.warm_idle_sec,
        )
        if req.restore_state_key is not None:
            await self.restore_state(page.context, req.restore_state_key)
        return BrowserAcquireResult(
            page=page,
            context=page.context,
            browser_id=req.endpoint_key,
            proxy_id=self._proxy_id(req.proxy_policy),
            cold_start=cold_start,
            endpoint_key=req.endpoint_key,
            context_signature_hash=req.context_signature.stable_hash(),
        )

    async def fetch(self, page: Any, req: BrowserFetchRequest) -> BrowserFetchResult:
        wait_policy = req.wait_policy
        timeout = req.navigation_timeout_ms
        if wait_policy.startswith(SELECTOR_PREFIX):
            css = wait_policy[len(SELECTOR_PREFIX) :]
            if not css:
                raise ValueError("wait_policy selector: требуется непустой CSS")
            response = await page.goto(
                req.url,
                wait_until="domcontentloaded",
                timeout=timeout,
            )
            await page.wait_for_selector(css, timeout=timeout)
        elif wait_policy == "domcontentloaded":
            response = await page.goto(
                req.url,
                wait_until="domcontentloaded",
                timeout=timeout,
            )
        elif wait_policy == "networkidle":
            response = await page.goto(
                req.url,
                wait_until="networkidle",
                timeout=timeout,
            )
        else:
            raise ValueError(
                f"Неизвестный wait_policy: {wait_policy} "
                f"(ожидались domcontentloaded, networkidle, selector:...)"
            )

        final_url = page.url
        status_code: Optional[int] = None
        response_headers: dict[str, str] = {}
        if response is not None:
            status_code = response.status
            response_headers = dict(response.headers)

        html: Optional[str] = await page.content()

        artifacts_root = Path(self._settings.artifacts_dir)
        artifacts_root.mkdir(parents=True, exist_ok=True)
        shot_ref: Optional[str] = None
        pdf_ref: Optional[str] = None
        snap_ref: Optional[str] = None
        token = uuid.uuid4().hex
        if req.screenshot:
            shot_path = artifacts_root / f"screenshot-{token}.png"
            sig = getattr(page.context, "_browser_runtime_signature", None)
            if sig is not None and getattr(sig, "emulate_locale_timezone_via_cdp", True) is False:
                # Lightpanda CDP часто не реализует Page.captureScreenshot и может падать.
                # В этом режиме пропускаем screenshot-артефакт.
                shot_ref = None
            else:
                await page.screenshot(path=str(shot_path), full_page=True)
                shot_ref = str(shot_path)
        if req.capture_pdf:
            pdf_path = artifacts_root / f"page-{token}.pdf"
            await page.pdf(path=str(pdf_path))
            pdf_ref = str(pdf_path)
        if req.snapshot:
            snap_path = artifacts_root / f"snapshot-{token}.html"
            snap_path.write_text(html if html is not None else "", encoding="utf-8")
            snap_ref = str(snap_path)

        return BrowserFetchResult(
            final_url=final_url,
            status_code=status_code,
            response_headers=response_headers,
            html=html,
            screenshot_ref=shot_ref,
            pdf_ref=pdf_ref,
            snapshot_ref=snap_ref,
            anti_bot_signals={},
        )

    async def exec_code(self, page: Any, code: str, *, timeout_ms: int) -> ExecCodeResult:
        if not code:
            raise ValueError("code не может быть пустым")
        if timeout_ms <= 0:
            raise ValueError("timeout_ms должен быть положительным")
        _assert_no_imports(code)
        console_events: list[dict[str, Any]] = []

        def on_console(msg: Any) -> None:
            console_events.append(
                {
                    "type": str(msg.type),
                    "text": msg.text,
                }
            )

        page.on("console", on_console)
        buf = io.StringIO()
        safe_builtins: dict[str, Any] = {
            "len": len,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "dict": dict,
            "list": list,
            "tuple": tuple,
            "set": set,
            "range": range,
            "min": min,
            "max": max,
            "sum": sum,
            "repr": repr,
            "isinstance": isinstance,
            "type": type,
            "abs": abs,
            "enumerate": enumerate,
            "zip": zip,
        }
        ns: dict[str, Any] = {
            "__builtins__": safe_builtins,
            "page": page,
            "context": page.context,
        }

        async def _run() -> None:
            with redirect_stdout(buf):
                wrapped = "async def __user_main__():\n"
                for line in code.splitlines():
                    wrapped += f"    {line}\n"
                if wrapped.endswith("async def __user_main__():\n"):
                    raise ValueError("code не может быть пустым")
                exec(wrapped, ns, ns)  # noqa: S102
                main = ns.get("__user_main__")
                if not callable(main):
                    raise RuntimeError("exec_code: __user_main__ не определён")
                res = main()
                if asyncio.iscoroutine(res):
                    out = await res
                else:
                    out = res
                if out is not None:
                    print(out)

        try:
            await asyncio.wait_for(_run(), timeout=timeout_ms / 1000.0)
            return ExecCodeResult(
                ok=True,
                stdout=buf.getvalue(),
                console_events=console_events,
                dom_diff_ref=None,
                error=None,
            )
        except Exception as exc:
            return ExecCodeResult(
                ok=False,
                stdout=buf.getvalue(),
                console_events=console_events,
                dom_diff_ref=None,
                error=str(exc),
            )
        finally:
            page.remove_listener("console", on_console)

    async def save_state(self, context: Any, shared_storage_key: str) -> str:
        pages = context.pages
        if len(pages) == 0:
            raise RuntimeError("Нет страниц в контексте для сохранения состояния")
        page = pages[0]
        return await self._store.capture_from(
            context,
            page,
            shared_storage_key=shared_storage_key,
            last_snapshot_ref=None,
        )

    async def restore_state(self, context: Any, state_key: str) -> None:
        for p in context.pages:
            url = p.url
            if url.startswith("about:"):
                continue
            origin = origin_from_url(url)
            entries = self._store.session_storage_for_origin(state_key, origin)
            if len(entries) == 0:
                continue
            await p.evaluate(
                """(entries) => {
                    for (const [k, v] of Object.entries(entries)) {
                        sessionStorage.setItem(k, v);
                    }
                }""",
                entries,
            )

    async def release(self, page: Any) -> None:
        await self._leases.release_page(
            page,
            warm_idle_sec=self._settings.warm_idle_sec,
        )


def _assert_no_imports(source: str) -> None:
    tree = ast.parse(source, mode="exec")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ValueError("Запрещён import в exec_code")

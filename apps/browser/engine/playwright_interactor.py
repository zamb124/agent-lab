"""
Playwright-реализация BrowserInteractor (§17).
"""

from __future__ import annotations

from apps.browser.engine.cdp_pool import CDPConnectionPool
from apps.browser.engine.page_lease_manager import PageLeaseManager
from apps.browser.engine.session_store import SessionStateStore, origin_from_url
from apps.browser.engine.types import (
    SELECTOR_PREFIX,
    BrowserAcquireRequest,
    BrowserAcquireResult,
    BrowserContextHandle,
    BrowserFetchRequest,
    BrowserFetchResult,
    BrowserPage,
    BrowserRuntimeSettingsView,
    BrowserStorageState,
    ContextSignature,
)
from core.files.processors import FileProcessor


class PlaywrightBrowserInteractor:
    """
    Реализация `BrowserInteractor` поверх Playwright + CDP.

    Мотивация:
    - Сконцентрировать все "браузерные действия" в одном слое: acquire/fetch/state/release.
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
    - Произвольный пользовательский код не исполняется внутри browser runtime.

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
        file_processor: FileProcessor,
    ) -> None:
        self._pool: CDPConnectionPool = pool
        self._store: SessionStateStore = session_store
        self._leases: PageLeaseManager = lease_manager
        self._settings: BrowserRuntimeSettingsView = settings
        self._file_processor: FileProcessor = file_processor

    def _cdp_url(self, endpoint_key: str) -> str:
        urls = self._settings.cdp_urls_by_endpoint
        if endpoint_key not in urls:
            raise KeyError(f"Нет CDP URL для endpoint_key={endpoint_key}")
        url = urls[endpoint_key]
        if not url:
            raise ValueError(f"Пустой CDP URL для endpoint_key={endpoint_key}")
        return url

    @staticmethod
    def _proxy_id(proxy_policy: str) -> str | None:
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
        storage_state: BrowserStorageState | None = None
        if req.restore_state_key is not None:
            blob = await self._store.get(req.restore_state_key)
            if blob.proxy_policy != req.context_signature.proxy_policy:
                raise ValueError("restore_state_key не совместим: proxy_policy отличается")
            if blob.anti_bot_tier != req.context_signature.anti_bot_tier:
                raise ValueError("restore_state_key не совместим: anti_bot_tier отличается")
            if blob.locale != req.context_signature.locale:
                raise ValueError("restore_state_key не совместим: locale отличается")
            if blob.timezone_id != req.context_signature.timezone_id:
                raise ValueError("restore_state_key не совместим: timezone_id отличается")
            if blob.user_agent != req.context_signature.user_agent:
                raise ValueError("restore_state_key не совместим: user_agent отличается")
            if blob.page_mode != req.context_signature.page_mode:
                raise ValueError("restore_state_key не совместим: page_mode отличается")
            if blob.permissions_fingerprint != req.context_signature.permissions_fingerprint:
                raise ValueError("restore_state_key не совместим: permissions_fingerprint отличается")
            storage_state = await self._store.storage_state_for_new_context(req.restore_state_key)
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
            url = await self._store.current_url(req.restore_state_key)
            _ = await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=req.timeout_ms,
            )
            await self._apply_session_storage(page, req.restore_state_key)
        return BrowserAcquireResult(
            page=page,
            context=page.context,
            browser_id=req.endpoint_key,
            proxy_id=self._proxy_id(req.proxy_policy),
            cold_start=cold_start,
            endpoint_key=req.endpoint_key,
            context_signature_hash=req.context_signature.stable_hash(),
        )

    async def fetch(self, page: BrowserPage, req: BrowserFetchRequest) -> BrowserFetchResult:
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
            _ = await page.wait_for_selector(css, timeout=timeout)
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
                + "(ожидались domcontentloaded, networkidle, selector:...)"
            )

        final_url = page.url
        status_code: int | None = None
        response_headers: dict[str, str] = {}
        if response is not None:
            status_code = response.status
            response_headers = dict(response.headers)

        html = await page.content()

        shot_ref: str | None = None
        pdf_ref: str | None = None
        snap_ref: str | None = None
        if req.screenshot:
            shot_bytes = await page.screenshot(
                type="png",
                full_page=False,
                timeout=5_000,
                animations="disabled",
            )
            shot_ref = await self._store_artifact(
                data=shot_bytes,
                original_name="page.png",
                content_type="image/png",
                final_url=final_url,
            )
        if req.capture_pdf:
            pdf_bytes = await page.pdf()
            pdf_ref = await self._store_artifact(
                data=pdf_bytes,
                original_name="page.pdf",
                content_type="application/pdf",
                final_url=final_url,
            )
        if req.snapshot:
            snap_ref = await self._store_artifact(
                data=html.encode("utf-8"),
                original_name="snapshot.html",
                content_type="text/html",
                final_url=final_url,
            )

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

    async def _store_artifact(
        self,
        *,
        data: bytes,
        original_name: str,
        content_type: str,
        final_url: str,
    ) -> str:
        """
        Сохранить артефакт навигации (скриншот/pdf/html) в S3 и вернуть file_id.

        Локальные пути не возвращаем: file_id — платформенная retrievable-ссылка,
        которую вызывающие сервисы/агенты читают через файловый API.
        """
        record = await self._file_processor.process_file_from_bytes(
            data=data,
            original_name=original_name,
            content_type=content_type,
            metadata={"source": "browser_fetch", "final_url": final_url},
            public=False,
        )
        return record.file_id

    async def save_state(self, context: BrowserContextHandle, shared_storage_key: str) -> str:
        pages = context.pages
        if len(pages) == 0:
            raise RuntimeError("Нет страниц в контексте для сохранения состояния")
        page = pages[0]
        signature: ContextSignature = await self._leases.context_signature_for_context(context)
        return await self._store.capture_from(
            context,
            page,
            shared_storage_key=shared_storage_key,
            context_signature=signature,
            last_snapshot_ref=None,
        )

    async def restore_state(self, context: BrowserContextHandle, state_key: str) -> None:
        for p in context.pages:
            url = p.url
            if url.startswith("about:"):
                continue
            origin = origin_from_url(url)
            entries = await self._store.session_storage_for_origin(state_key, origin)
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

    async def _apply_session_storage(self, page: BrowserPage, state_key: str) -> None:
        origin = origin_from_url(page.url)
        entries = await self._store.session_storage_for_origin(state_key, origin)
        if len(entries) == 0:
            return
        await page.evaluate(
            """(entries) => {
                for (const [k, v] of Object.entries(entries)) {
                    sessionStorage.setItem(k, v);
                }
            }""",
            entries,
        )

    async def release(self, page: BrowserPage) -> None:
        await self._leases.release_page(
            page,
            warm_idle_sec=self._settings.warm_idle_sec,
        )

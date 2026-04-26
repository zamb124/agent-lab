"""
Адаптер Playwright: делегирование BrowserInteractor и AX visibility с лимитом budget.
"""

from __future__ import annotations

from typing import Any

from apps.browser.control.ax_snapshot import ax_snapshot_dict_from_page
from apps.browser.control.ax_visibility import flatten_ax_nodes, prune_visibility_nodes
from apps.browser.control.types import (
    BrowserCapabilityError,
    BrowserControlFeatures,
)
from apps.browser.runtime.contracts import BrowserInteractor
from apps.browser.runtime.types import (
    BrowserAcquireRequest,
    BrowserAcquireResult,
    BrowserFetchRequest,
    BrowserFetchResult,
    ExecCodeResult,
)


def _exec_result_to_dict(r: ExecCodeResult) -> dict[str, Any]:
    return {
        "ok": r.ok,
        "stdout": r.stdout,
        "console_events": r.console_events,
        "dom_diff_ref": r.dom_diff_ref,
        "error": r.error,
    }


def _collect_backend_node_ids(node: dict[str, Any] | None, out: list[int]) -> None:
    if node is None or not isinstance(node, dict):
        return
    raw = node.get("backendDOMNodeId")
    if isinstance(raw, int):
        out.append(raw)
    ch = node.get("children")
    if isinstance(ch, list):
        for c in ch:
            if isinstance(c, dict):
                _collect_backend_node_ids(c, out)


class PlaywrightAdapter:
    """
    Рабочая реализация `BrowserControlAdapter` на базе `BrowserInteractor`.

    Связи:
    - Делегирует start/navigate/run_action/stop в interactor.
    - Строит visibility/accessibility/listeners через AX/CDP утилиты.

    Состояние:
    - Ссылка на interactor конкретного runtime.

    Инварианты:
    - `features()` правдиво описывает доступные возможности Playwright backend-а.
    - Ошибки CDP listeners маппятся в `BrowserCapabilityError`.

    Мотивация:
    - Отделить внешний control-контракт от деталей Playwright/AX/CDP.

    Переиспользование:
    - Стоит: как основной production-адаптер для CDP-совместимых движков.
    - Не стоит: для backend-а без Playwright API; тогда нужен отдельный адаптер.
    """
    def __init__(self, interactor: BrowserInteractor) -> None:
        self._interactor = interactor

    def features(self) -> BrowserControlFeatures:
        return BrowserControlFeatures(
            supports_js_injection_dom_tree=True,
            supports_cdp_dom_snapshot=True,
            supports_cdp_event_listeners=True,
            supports_ax_tree=True,
            supports_selector_map=False,
        )

    async def start(self, req: BrowserAcquireRequest) -> BrowserAcquireResult:
        return await self._interactor.acquire(req)

    async def navigate(self, page: Any, req: BrowserFetchRequest) -> BrowserFetchResult:
        return await self._interactor.fetch(page, req)

    async def run_action(self, page: Any, code: str, *, timeout_ms: int) -> dict[str, Any]:
        result = await self._interactor.exec_code(page, code, timeout_ms=timeout_ms)
        return _exec_result_to_dict(result)

    async def get_visibility_tree(
        self,
        page: Any,
        *,
        budget: int,
        emit_generic_role: bool,
    ) -> dict[str, Any]:
        if budget <= 0:
            raise ValueError("budget должен быть положительным")
        snap = await ax_snapshot_dict_from_page(page, emit_generic_role=emit_generic_role)
        url = page.url
        flat = flatten_ax_nodes(snap)
        return prune_visibility_nodes(flat, budget=budget, url=url)

    async def get_accessibility_tree(self, page: Any, *, emit_generic_role: bool) -> dict[str, Any]:
        snap = await ax_snapshot_dict_from_page(page, emit_generic_role=emit_generic_role)
        return {
            "schema": "browser.control.accessibility.v1",
            "url": page.url,
            "tree": snap,
        }

    async def get_dom_event_listeners(self, page: Any) -> dict[str, Any]:
        snap = await ax_snapshot_dict_from_page(page, emit_generic_role=False)
        backend_ids: list[int] = []
        if isinstance(snap, dict):
            _collect_backend_node_ids(snap, backend_ids)
        if len(backend_ids) == 0:
            return {
                "supported": False,
                "reason": "no_backend_node_ids_in_ax_snapshot",
                "items": [],
            }
        try:
            cdp = await page.context.new_cdp_session(page)
            await cdp.send("DOM.enable")
        except Exception as exc:
            raise BrowserCapabilityError(
                "cdp_event_listeners_unavailable",
                "Не удалось открыть CDP session или DOM.enable",
                details={"error": str(exc)},
            ) from exc

        items: list[dict[str, Any]] = []
        for bid in backend_ids[:50]:
            try:
                resolved = await cdp.send(
                    "DOM.resolveNode",
                    {"backendNodeId": bid},
                )
                obj = resolved.get("object") if isinstance(resolved, dict) else None
                if not isinstance(obj, dict):
                    continue
                object_id = obj.get("objectId")
                if not isinstance(object_id, str):
                    continue
                listeners_result = await cdp.send(
                    "DOMDebugger.getEventListeners",
                    {"objectId": object_id},
                )
                listeners_raw = (
                    listeners_result.get("listeners")
                    if isinstance(listeners_result, dict)
                    else None
                )
                if not isinstance(listeners_raw, list):
                    listeners_raw = []
                listeners_norm: list[dict[str, Any]] = []
                for li in listeners_raw:
                    if not isinstance(li, dict):
                        continue
                    listeners_norm.append(
                        {
                            "type": li.get("type"),
                            "useCapture": li.get("useCapture"),
                            "passive": li.get("passive"),
                            "once": li.get("once"),
                            "scriptId": li.get("scriptId"),
                            "lineNumber": li.get("lineNumber"),
                            "columnNumber": li.get("columnNumber"),
                            "handler": li.get("handler"),
                            "originalHandler": li.get("originalHandler"),
                        }
                    )
                items.append(
                    {
                        "backendNodeId": bid,
                        "listeners": listeners_norm,
                    }
                )
            except Exception:
                continue
        return {
            "supported": True,
            "reason": None,
            "items": items,
        }

    async def stop(self, page: Any) -> None:
        await self._interactor.release(page)

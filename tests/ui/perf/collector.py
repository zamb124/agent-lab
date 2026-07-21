"""Playwright collector: сеть, navigation Timing, long tasks."""

from __future__ import annotations

import contextvars
import time
from typing import cast
from urllib.parse import urlsplit

from playwright.async_api import BrowserContext, Page, Request, Response

from tests.ui.e2e_worker import ui_e2e_worker_id
from tests.ui.perf.models import (
    UiPerfLongTask,
    UiPerfNavigation,
    UiPerfRequest,
    UiPerfTestReport,
)
from tests.ui.perf.report import rebuild_summary, write_test_report

_SLOWEST_REQUESTS_N = 20
_LONG_TASKS_TOP_N = 30

_LONG_TASK_INIT_SCRIPT = """
(() => {
  if (window.__UI_PERF_LONG_TASKS__) {
    return;
  }
  window.__UI_PERF_LONG_TASKS__ = [];
  if (typeof PerformanceObserver === 'undefined') {
    return;
  }
  try {
    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        window.__UI_PERF_LONG_TASKS__.push({
          duration: entry.duration,
          startTime: entry.startTime,
          name: entry.name || 'longtask',
        });
      }
    });
    observer.observe({ type: 'longtask', buffered: true });
  } catch (_err) {
    // Safari / older Chromium without longtask — ignore.
  }
})();
"""

_NAVIGATION_SNAPSHOT_JS = """
() => {
  const entries = performance.getEntriesByType('navigation');
  if (!entries || entries.length === 0) {
    return null;
  }
  const nav = entries[entries.length - 1];
  return {
    url: location.href,
    responseStart: nav.responseStart,
    domContentLoaded: nav.domContentLoadedEventEnd,
    load: nav.loadEventEnd,
    transferSize: typeof nav.transferSize === 'number' ? nav.transferSize : null,
  };
}
"""

_LONG_TASKS_SNAPSHOT_JS = """
() => {
  const items = window.__UI_PERF_LONG_TASKS__ || [];
  return items.map((item) => ({
    duration: item.duration,
    startTime: item.startTime,
    name: item.name || 'longtask',
  }));
}
"""

_current_collector: contextvars.ContextVar[UiPerfCollector | None] = contextvars.ContextVar(
    "ui_perf_collector",
    default=None,
)


def get_current_collector() -> UiPerfCollector | None:
    return _current_collector.get()


def set_current_collector(collector: UiPerfCollector | None) -> contextvars.Token[UiPerfCollector | None]:
    return _current_collector.set(collector)


def reset_current_collector(token: contextvars.Token[UiPerfCollector | None]) -> None:
    _current_collector.reset(token)


def service_prefix_from_path(path: str) -> str:
    if not path.startswith("/"):
        return ""
    parts = [part for part in path.split("/") if part]
    if not parts:
        return "/"
    return f"/{parts[0]}/"


def _public_url(raw_url: str) -> tuple[str, str]:
    """Возвращает (url без fragment, path+query)."""
    split = urlsplit(raw_url)
    path = split.path or "/"
    if split.query:
        path_with_query = f"{path}?{split.query}"
    else:
        path_with_query = path
    url = f"{split.scheme}://{split.netloc}{path_with_query}"
    return url, path_with_query


class UiPerfCollector:
    """Собирает метрики одного UI E2E теста."""

    nodeid: str
    worker_id: str
    _started_at: float
    _pending_started: dict[int, float]
    _requests: list[UiPerfRequest]
    _navigations: list[UiPerfNavigation]
    _long_tasks: list[UiPerfLongTask]
    _captured_context_ids: set[int]
    _attached_context_ids: set[int]

    def __init__(self, nodeid: str) -> None:
        self.nodeid = nodeid
        self.worker_id = ui_e2e_worker_id()
        self._started_at = time.monotonic()
        self._pending_started = {}
        self._requests = []
        self._navigations = []
        self._long_tasks = []
        self._captured_context_ids = set()
        self._attached_context_ids = set()

    async def attach_to_context(self, context: BrowserContext) -> None:
        context_id = id(context)
        if context_id in self._attached_context_ids:
            return
        self._attached_context_ids.add(context_id)
        _ = await context.add_init_script(_LONG_TASK_INIT_SCRIPT)
        context.on("request", self._on_request)
        context.on("response", self._on_response)
        context.on("requestfailed", self._on_request_failed)

    async def capture_context(self, context: BrowserContext) -> None:
        """Снимок navigation/long tasks до context.close() (teardown page-фикстур)."""
        context_id = id(context)
        if context_id in self._captured_context_ids:
            return
        self._captured_context_ids.add(context_id)
        for page in context.pages:
            page_navs, page_tasks = await self._snapshot_page(page)
            self._navigations.extend(page_navs)
            self._long_tasks.extend(page_tasks)

    def _on_request(self, request: Request) -> None:
        self._pending_started[id(request)] = time.monotonic()

    def _on_response(self, response: Response) -> None:
        request = response.request
        started = self._pending_started.pop(id(request), None)
        duration_ms: float | None = None
        if started is not None:
            duration_ms = (time.monotonic() - started) * 1000.0
        url, path = _public_url(response.url)
        transfer_raw = response.headers.get("content-length")
        transfer_size: int | None = None
        if transfer_raw is not None and transfer_raw.isdigit():
            transfer_size = int(transfer_raw)
        self._requests.append(
            UiPerfRequest(
                method=request.method,
                url=url,
                path=path,
                service_prefix=service_prefix_from_path(urlsplit(response.url).path or "/"),
                status=response.status,
                resource_type=request.resource_type,
                duration_ms=duration_ms,
                transfer_size=transfer_size,
                failed=False,
            )
        )

    def _on_request_failed(self, request: Request) -> None:
        started = self._pending_started.pop(id(request), None)
        duration_ms: float | None = None
        if started is not None:
            duration_ms = (time.monotonic() - started) * 1000.0
        url, path = _public_url(request.url)
        failure = request.failure
        failure_text = failure if isinstance(failure, str) else None
        self._requests.append(
            UiPerfRequest(
                method=request.method,
                url=url,
                path=path,
                service_prefix=service_prefix_from_path(urlsplit(request.url).path or "/"),
                status=None,
                resource_type=request.resource_type,
                duration_ms=duration_ms,
                transfer_size=None,
                failed=True,
                failure_text=failure_text,
            )
        )

    async def _snapshot_page(self, page: Page) -> tuple[list[UiPerfNavigation], list[UiPerfLongTask]]:
        navigations: list[UiPerfNavigation] = []
        long_tasks: list[UiPerfLongTask] = []
        if page.is_closed():
            return navigations, long_tasks
        nav_raw = cast(object, await page.evaluate(_NAVIGATION_SNAPSHOT_JS))
        if nav_raw is not None:
            nav_map = _require_str_object_map(nav_raw, "navigation snapshot")
            url_value = nav_map.get("url")
            if not isinstance(url_value, str) or not url_value:
                raise ValueError("navigation snapshot url must be non-empty str")
            navigations.append(
                UiPerfNavigation(
                    url=url_value,
                    response_start_ms=_optional_float(nav_map.get("responseStart")),
                    dom_content_loaded_ms=_optional_float(nav_map.get("domContentLoaded")),
                    load_ms=_optional_float(nav_map.get("load")),
                    transfer_size=_optional_int(nav_map.get("transferSize")),
                )
            )
        tasks_raw = cast(object, await page.evaluate(_LONG_TASKS_SNAPSHOT_JS))
        if not isinstance(tasks_raw, list):
            raise ValueError("long tasks snapshot must be a list")
        for entry_raw in cast(list[object], tasks_raw):
            task_map = _require_str_object_map(entry_raw, "long task entry")
            duration = task_map.get("duration")
            start_time = task_map.get("startTime")
            name = task_map.get("name")
            if not isinstance(duration, (int, float)) or isinstance(duration, bool):
                raise ValueError("long task duration must be a number")
            if not isinstance(start_time, (int, float)) or isinstance(start_time, bool):
                raise ValueError("long task startTime must be a number")
            if not isinstance(name, str):
                raise ValueError("long task name must be a str")
            long_tasks.append(
                UiPerfLongTask(
                    duration_ms=float(duration),
                    start_time_ms=float(start_time),
                    name=name,
                )
            )
        return navigations, long_tasks

    async def finalize(self) -> UiPerfTestReport:
        wall_ms = (time.monotonic() - self._started_at) * 1000.0
        error_4xx = 0
        error_5xx = 0
        failed_count = 0
        unique_paths: set[str] = set()
        for req in self._requests:
            unique_paths.add(f"{req.method} {req.path}")
            if req.failed:
                failed_count += 1
            if req.status is None:
                continue
            if 400 <= req.status < 500:
                error_4xx += 1
            elif req.status >= 500:
                error_5xx += 1

        timed = [req for req in self._requests if req.duration_ms is not None]
        slowest = sorted(
            timed,
            key=lambda item: item.duration_ms if item.duration_ms is not None else 0.0,
            reverse=True,
        )[:_SLOWEST_REQUESTS_N]

        long_tasks_sorted = sorted(
            self._long_tasks,
            key=lambda item: item.duration_ms,
            reverse=True,
        )
        long_top = long_tasks_sorted[:_LONG_TASKS_TOP_N]
        long_total = sum(item.duration_ms for item in self._long_tasks)
        long_max = long_tasks_sorted[0].duration_ms if long_tasks_sorted else 0.0

        report = UiPerfTestReport(
            nodeid=self.nodeid,
            worker_id=self.worker_id,
            wall_ms=wall_ms,
            request_count=len(self._requests),
            unique_paths=len(unique_paths),
            error_4xx_count=error_4xx,
            error_5xx_count=error_5xx,
            failed_request_count=failed_count,
            long_task_count=len(self._long_tasks),
            long_task_total_ms=long_total,
            long_task_max_ms=long_max,
            requests=self._requests,
            slowest_requests=slowest,
            navigations=list(self._navigations),
            long_tasks=long_top,
        )
        _ = write_test_report(report)
        _ = rebuild_summary()
        return report


def _require_str_object_map(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    result: dict[str, object] = {}
    for key_raw, item in cast(dict[object, object], value).items():
        if not isinstance(key_raw, str):
            raise ValueError(f"{label} keys must be str")
        result[key_raw] = item
    return result


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("bool is not a float metric")
    if isinstance(value, (int, float)):
        return float(value)
    raise ValueError(f"expected number, got {type(value).__name__}")


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("bool is not an int metric")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    raise ValueError(f"expected int, got {type(value).__name__}")

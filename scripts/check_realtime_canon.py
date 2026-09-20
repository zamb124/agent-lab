#!/usr/bin/env python3
"""CI: user WS только Centrifugo /realtime; HTTP к CF только из bus."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ERRORS: list[str] = []

USER_WS_RE = re.compile(r"/api/ws/notifications")
CONNECTION_TOKEN_RE = re.compile(r"connection_token")
CENTRIFUGO_HTTP_RE = re.compile(r"/api/(?:publish|presence_stats|presence)\b")
CONNECT_PROXY_RE = re.compile(r"connect.proxy|connect_proxy", re.I)

SCAN_DIRS = (
    ROOT / "apps",
    ROOT / "core",
    ROOT / "core" / "frontend" / "static" / "lib",
)

SKIP_PARTS = {
    "node_modules",
    "dist",
    "vendor",
    "__pycache__",
}

ALLOWED_CENTRIFUGO_HTTP = {
    ROOT / "core" / "realtime" / "centrifugo_client.py",
    ROOT / "apps" / "realtime",
}

ALLOWED_USER_WS_MENTION: set[Path] = set()


def fail(message: str) -> None:
    ERRORS.append(message)


def _skip(path: Path) -> bool:
    return any(part in SKIP_PARTS for part in path.parts)


def _is_allowed_cf_http(path: Path) -> bool:
    for allowed in ALLOWED_CENTRIFUGO_HTTP:
        try:
            path.relative_to(allowed)
            return True
        except ValueError:
            continue
        except OSError:
            continue
    return path == ROOT / "core" / "realtime" / "centrifugo_client.py"


def _iter_source() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_DIRS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if _skip(path):
                continue
            if path.suffix not in {".py", ".js", ".ts", ".tsx"}:
                continue
            if not path.is_file():
                continue
            files.append(path)
    return files


def main() -> int:
    for path in _iter_source():
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT)
        for match in USER_WS_RE.finditer(text):
            if path in ALLOWED_USER_WS_MENTION:
                continue
            if "voice" in path.parts and "session" in text[max(0, match.start() - 80) : match.end() + 80]:
                continue
            line = text[: match.start()].count("\n") + 1
            fail(f"{rel}:{line}: user WS path /api/ws/notifications is forbidden; use /realtime")
        for match in CONNECTION_TOKEN_RE.finditer(text):
            line = text[: match.start()].count("\n") + 1
            fail(f"{rel}:{line}: connection_token is forbidden; SESSION JWT is Centrifugo JWT")
        if CENTRIFUGO_HTTP_RE.search(text) and not _is_allowed_cf_http(path):
            if "centrifugo" in text.lower() or "Centrifugo" in text:
                line = 1
                fail(f"{rel}:{line}: Centrifugo HTTP API only from apps/realtime and core/realtime")
        if CONNECT_PROXY_RE.search(text) and path.suffix == ".py" and "apps" in path.parts:
            if "rpc" in text and "connect proxy" in text.lower():
                line = text.lower().find("connect") + 1
                fail(f"{rel}: Centrifugo connect-proxy is forbidden")
        if "sync/presence/changed" in text:
            fail(f"{rel}: leftover unpublished event sync/presence/changed")
        if "sync:ws:presence:" in text:
            fail(f"{rel}: leftover Redis key sync:ws:presence")
        if 'RouteRule("/sync/ws"' in text:
            fail(f"{rel}: leftover FastAPI /sync/ws route")

    factory = ROOT / "core" / "app" / "factory.py"
    factory_text = factory.read_text(encoding="utf-8")
    if "ws_router" in factory_text or "create_ws_router" in factory_text:
        fail("core/app/factory.py: per-pod ws_router must not be mounted")
    if "start_redis_listener" in factory_text:
        fail("core/app/factory.py: per-pod platform:events tail is forbidden")

    proxy = ROOT / "core" / "middleware" / "dev_inter_service_proxy.py"
    proxy_text = proxy.read_text(encoding="utf-8")
    if "user WebSocket /realtime must not be proxied" not in proxy_text:
        fail("dev_inter_service_proxy.py must refuse user WSS /realtime")

    for path in (ROOT / "apps").rglob("*.py"):
        if _skip(path):
            continue
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT)
        if "is_user_sync_ws_online" in text:
            fail(f"{rel}: use core.realtime.presence.is_user_connected, not is_user_sync_ws_online")
        if "sync/presence/changed" in text:
            fail(f"{rel}: leftover unpublished event sync/presence/changed")
        if "sync:ws:presence:" in text:
            fail(f"{rel}: leftover Redis key sync:ws:presence")
        if 'RouteRule("/sync/ws"' in text:
            fail(f"{rel}: leftover FastAPI /sync/ws route")
        if re.search(r"^class Operation\b", text, re.M):
            fail(f"{rel}: class Operation живёт только в core/websocket/operation.py")

    for path in (ROOT / ".cursor" / "rules").rglob("*.mdc"):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT)
        if "platform/work_items" in text or "platform/work_item_" in text:
            fail(f"{rel}: leftover platform/work_item_* — используй worktracker/work_item_*")
        if "{request_id, type, payload}" in text:
            fail(f"{rel}: WS кадр = PlatformEvent, не {{request_id, type, payload}}")

    for path in (ROOT / "tests").rglob("*.py"):
        if _skip(path):
            continue
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT)
        if "platform_notification_manager_redis" in text:
            fail(f"{rel}: leftover no-op fixture platform_notification_manager_redis")
        if "is_user_sync_ws_online" in text:
            fail(f"{rel}: use is_user_connected, not is_user_sync_ws_online")
        if "legacy WS frame" in text:
            fail(f"{rel}: leftover legacy WS frame translator")
        if "sync:ws:presence:" in text:
            fail(f"{rel}: leftover Redis key sync:ws:presence")
        if "sync/presence/changed" in text:
            fail(f"{rel}: leftover unpublished event sync/presence/changed")

    realtime_tests = ROOT / "tests" / "realtime"
    if realtime_tests.exists():
        for path in realtime_tests.rglob("*.py"):
            if _skip(path):
                continue
            text = path.read_text(encoding="utf-8")
            rel = path.relative_to(ROOT)
            for needle in (
                "monkeypatch",
                "MagicMock",
                "AsyncMock",
                "unittest.mock",
                "pytest_mock",
            ):
                if needle in text:
                    fail(f"{rel}: realtime tests must not use {needle}")

    if ERRORS:
        print("check_realtime_canon: FAIL")
        for item in ERRORS:
            print(item)
        return 1
    print("check_realtime_canon: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

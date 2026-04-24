"""Тесты маршрутизации AuthMiddleware для Sync."""

import pytest
from core.middleware.auth.route_config import RouteMatcher, path_allows_spa_fallback


def test_login_page_is_public() -> None:
    matcher = RouteMatcher()
    rule = matcher.match("/login")
    assert rule is not None
    assert rule.context_type == "anonymous"
    assert rule.auth_required is False


def test_sync_ui_shell_is_public() -> None:
    # SPA-оболочка загружается без auth — JS сам вызывает checkAuth() и redirectToAuth()
    matcher = RouteMatcher()
    for path in ("/sync", "/sync/", "/sync/chat", "/sync/c/some-channel-id"):
        rule = matcher.match(path)
        assert rule is not None, f"no rule for {path}"
        assert rule.context_type == "anonymous", f"{path}: expected anonymous"
        assert rule.auth_required is False, f"{path}: expected auth_required=False"


def test_sync_ws_is_public_middleware_auth_in_handler() -> None:
    matcher = RouteMatcher()
    rule = matcher.match("/sync/ws")
    assert rule is not None
    assert rule.context_type == "anonymous"
    assert rule.auth_required is False


def test_prefixed_auth_providers_matches() -> None:
    matcher = RouteMatcher()
    rule = matcher.match("/frontend/api/auth/providers")
    assert rule is not None
    assert rule.auth_required is True


def test_frontend_health_is_public_anonymous() -> None:
    matcher = RouteMatcher()
    rule = matcher.match("/frontend/health")
    assert rule is not None
    assert rule.auth_required is False
    assert rule.context_type == "anonymous"


def test_sync_api_requires_auth() -> None:
    matcher = RouteMatcher()
    rule = matcher.match("/sync/api/v1/namespaces")
    assert rule is not None
    assert rule.context_type == "api"
    assert rule.auth_required is True


def test_sync_api_nested_paths_require_auth() -> None:
    """Вложенные REST-пути: fnmatch * в ROUTE_RULES совпадает с несколькими сегментами."""
    matcher = RouteMatcher()
    for path in (
        "/sync/api/v1/channels/ch_1",
        "/sync/api/v1/channels/ch_1/messages",
    ):
        rule = matcher.match(path)
        assert rule is not None, path
        assert rule.context_type == "api", path
        assert rule.auth_required is True, path


def test_flows_api_nested_paths_require_auth() -> None:
    matcher = RouteMatcher()
    for path in (
        "/flows/api/v1/flows",
        "/flows/api/v1/flows/flow_123",
        "/flows/api/v1/flows/flow_123/triggers",
    ):
        rule = matcher.match(path)
        assert rule is not None, path
        assert rule.context_type == "api", path
        assert rule.auth_required is True, path


def test_flows_telegram_trigger_webhook_is_public_anonymous() -> None:
    """POST Telegram Bot update: тот же путь, что setWebhook, без JWT (как у серверов Telegram)."""
    matcher = RouteMatcher()
    rule = matcher.match("/flows/api/v1/triggers/telegram/flow_x/trigger_y")
    assert rule is not None
    assert rule.context_type == "anonymous"
    assert rule.auth_required is False


def test_sync_ui_static_is_public() -> None:
    matcher = RouteMatcher()
    rule = matcher.match("/sync/ui/static/index.js")
    assert rule is not None
    assert rule.context_type == "anonymous"
    assert rule.auth_required is False


def test_spa_fallback_path_allows_unknown_browser_path() -> None:
    assert path_allows_spa_fallback("/d3423") is True
    assert path_allows_spa_fallback("/some-page") is True


def test_spa_fallback_path_excludes_api_and_services() -> None:
    assert path_allows_spa_fallback("/api/foo") is False
    assert path_allows_spa_fallback("/flows/v1/x") is False
    assert path_allows_spa_fallback("/sync/api/v1/namespaces") is False


def test_no_legacy_auth_routes() -> None:
    matcher = RouteMatcher()
    legacy_paths = ["/auth", "/chat", "/ws", "/api/auth/login", "/api/auth/register", "/api/channels/"]
    for path in legacy_paths:
        rule = matcher.match(path)
        if rule is not None:
            assert rule.context_type not in ("anonymous",) or path in ("/auth",), (
                f"Legacy Sync path {path!r} matched unexpectedly: {rule}"
            )


def test_main_page_is_public_anonymous() -> None:
    """Главная страница / должна быть публичной без авторизации и компании."""
    matcher = RouteMatcher()
    rule = matcher.match("/")
    assert rule is not None
    assert rule.context_type == "anonymous"
    assert rule.auth_required is False


def test_products_pages_are_public_anonymous() -> None:
    """Страницы продуктов должны быть публичными без авторизации."""
    matcher = RouteMatcher()
    for path in ("/products/agents", "/products/rag", "/products/crm", "/products/sync"):
        rule = matcher.match(path)
        assert rule is not None, f"no rule for {path}"
        assert rule.context_type == "anonymous", f"{path}: expected anonymous"
        assert rule.auth_required is False, f"{path}: expected auth_required=False"

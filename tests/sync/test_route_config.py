"""Тесты маршрутизации AuthMiddleware для Sync."""

import pytest
from core.middleware.auth.route_config import RouteMatcher


def test_sync_ui_shell_is_public() -> None:
    # SPA-оболочка загружается без auth — JS сам вызывает checkAuth() и redirectToAuth()
    matcher = RouteMatcher()
    for path in ("/sync", "/sync/", "/sync/chat", "/sync/spaces"):
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


def test_sync_api_requires_auth() -> None:
    matcher = RouteMatcher()
    rule = matcher.match("/sync/api/v1/spaces/")
    assert rule is not None
    assert rule.context_type == "api"
    assert rule.auth_required is True


def test_sync_ui_static_is_public() -> None:
    matcher = RouteMatcher()
    rule = matcher.match("/sync/ui/static/index.js")
    assert rule is not None
    assert rule.context_type == "anonymous"
    assert rule.auth_required is False


def test_no_legacy_auth_routes() -> None:
    matcher = RouteMatcher()
    legacy_paths = ["/auth", "/chat", "/ws", "/api/auth/login", "/api/auth/register", "/api/spaces/"]
    for path in legacy_paths:
        rule = matcher.match(path)
        if rule is not None:
            assert rule.context_type not in ("anonymous",) or path in ("/auth",), (
                f"Legacy Sync path {path!r} matched unexpectedly: {rule}"
            )

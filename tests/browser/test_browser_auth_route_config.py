"""Auth route config для browser runtime (readiness probe, control-plane)."""

from __future__ import annotations

from core.middleware.auth.route_config import RouteMatcher


def test_route_matcher_marks_browser_health_cdp_as_anonymous() -> None:
    """Readiness probe /browser/api/v1/health/cdp не блокируется AuthMiddleware."""
    matcher = RouteMatcher()

    rule = matcher.match("/browser/api/v1/health/cdp")
    assert rule is not None
    assert rule.context_type == "anonymous"
    assert rule.auth_required is False


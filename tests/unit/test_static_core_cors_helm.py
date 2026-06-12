from pathlib import Path

_CHART_ROOT = Path(__file__).parents[2] / "deploy" / "helm" / "agent-lab"
_INGRESS_TEMPLATE = _CHART_ROOT / "templates" / "80-ingress" / "platform-ingress.yaml"
_CORS_MIDDLEWARE_TEMPLATE = (
    _CHART_ROOT / "templates" / "80-ingress" / "static-core-cors-middleware.yaml"
)


def test_static_core_has_dedicated_cors_ingress():
    template = _INGRESS_TEMPLATE.read_text(encoding="utf-8")

    assert "name: platform-static-core" in template
    assert "traefik.ingress.kubernetes.io/router.priority: \"20\"" in template
    assert "path: /static/core" in template
    assert "pathType: Prefix" in template
    assert "static-core-cors@kubernetescrd" in template
    assert "compress@kubernetescrd" in template


def test_static_core_cors_middleware_allows_public_module_fetches():
    template = _CORS_MIDDLEWARE_TEMPLATE.read_text(encoding="utf-8")

    assert "kind: Middleware" in template
    assert "name: static-core-cors" in template
    assert "accessControlAllowMethods:" in template
    assert "- GET" in template
    assert "- HEAD" in template
    assert "- OPTIONS" in template
    assert "accessControlAllowHeaders:" in template
    assert "- \"*\"" in template
    assert "accessControlAllowOriginList:" in template
    assert "accessControlMaxAge: 86400" in template

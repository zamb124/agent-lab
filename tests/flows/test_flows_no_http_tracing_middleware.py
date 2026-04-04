"""Сервис flows не создаёт HTTP request spans через TracingMiddleware (трейсинг — осмысленные операции)."""


def test_flows_app_has_no_tracing_middleware():
    from apps.flows.main import app
    from core.tracing.middleware import TracingMiddleware

    middleware_classes = [m.cls for m in app.user_middleware]
    assert TracingMiddleware not in middleware_classes

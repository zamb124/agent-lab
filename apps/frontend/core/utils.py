"""
Вспомогательные функции для работы фронтенда
"""

from fastapi import Request
from fastapi.responses import HTMLResponse
from apps.frontend.core.template_loader import get_templates
from apps.frontend.core.plugin_loader import get_plugins_for_template


templates = get_templates()


def is_htmx_request(request: Request) -> bool:
    """Проверяет, является ли запрос HTMX запросом"""
    return request.headers.get("HX-Request") == "true"


async def render_with_dashboard(
    request: Request,
    content_template: str,
    context: dict,
    content_url: str,
) -> HTMLResponse:
    """
    Универсальная функция для рендеринга контента с поддержкой HTMX и прямых переходов.
    
    Args:
        request: FastAPI Request объект
        content_template: Имя шаблона с контентом (например, "bots.html")
        context: Контекст для рендеринга шаблона
        content_url: URL для загрузки контента через HTMX при прямом переходе
    
    Returns:
        HTMLResponse с фрагментом (для HTMX) или полным dashboard (для прямого перехода)
    """
    if is_htmx_request(request):
        context_with_request = {**context}
        if "request" not in context_with_request:
            context_with_request["request"] = request
        
        content_html = templates.get_template(content_template).render(**context_with_request)
        return HTMLResponse(content=content_html)
    
    plugin_data = get_plugins_for_template(request)
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "preload_url": content_url,
            **plugin_data
        }
    )

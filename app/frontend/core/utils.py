"""
Вспомогательные функции для работы фронтенда
"""

from fastapi import Request
from fastapi.responses import HTMLResponse
from app.frontend.core.template_loader import get_templates


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
        return templates.TemplateResponse(content_template, context)
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "preload_url": content_url,
        }
    )

"""
Публичные страницы (landing page и т.д.)
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.frontend.core.template_loader import get_templates

router = APIRouter(tags=["public-pages"])
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """Главная страница - лендинг Agents Lab"""
    # Проверяем, авторизован ли пользователь
    context = getattr(request.state, 'context', None)
    is_authenticated = (
        context and 
        context.user and 
        context.user.user_id != "anonymous"
    )
    
    return templates.TemplateResponse(
        "landing.html", 
        {
            "request": request, 
            "is_authenticated": is_authenticated
        }
    )


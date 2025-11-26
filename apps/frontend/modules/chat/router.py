"""
Роутер модуля Chat - страницы и виджеты чата
"""

from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse
from typing import Optional
from apps.frontend.core.template_loader import get_templates
from core.utils.tokens import get_token_service

router = APIRouter(prefix="/frontend/chat", tags=["chat-pages"])
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def chat_page(request: Request):
    """Главная страница чата"""
    return templates.TemplateResponse("chat.html", {"request": request})


@router.get("/widget", response_class=HTMLResponse)
async def chat_widget(request: Request, agent_id: str = None, session_id: str = None):
    """Виджет чата для встраивания"""
    return templates.TemplateResponse(
        "chat_widget.html",
        {"request": request, "agent_id": agent_id, "session_id": session_id},
    )


@router.get("/embed", response_class=HTMLResponse)
async def embed_chat(
    request: Request,
    token: str = Query(..., description="Токен доступа для встраивания"),
    flow_id: str = Query(..., description="ID flow для чата"),
    session_id: Optional[str] = Query(None, description="ID сессии (опционально)"),
    theme: Optional[str] = Query("light", description="Тема оформления (light/dark)"),
    width: Optional[str] = Query("400px", description="Ширина виджета"),
    height: Optional[str] = Query("600px", description="Высота виджета"),
    user_id: Optional[str] = Query(None, description="ID пользователя"),
    mode: Optional[str] = Query("widget", description="Режим отображения: widget (кнопка) или expanded (развернутый)")
):
    """
    Встраиваемый чат для внешних сайтов
    
    Параметры:
    - token: Токен доступа (обязательный)
    - flow_id: ID flow для чата (обязательный)
    - session_id: ID сессии для продолжения диалога (опционально)
    - theme: Тема оформления - light или dark (по умолчанию light)
    - width: Ширина виджета (по умолчанию 400px)
    - height: Высота виджета (по умолчанию 600px)
    - user_id: ID пользователя для персонализации (опционально)
    - mode: Режим отображения - widget (кнопка) или expanded (развернутый) (по умолчанию widget)
    
    Примеры использования:
    /frontend/chat/embed?token=abc123&flow_id=support_bot&mode=widget
    /frontend/chat/embed?token=abc123&flow_id=support_bot&mode=expanded&width=500px&height=700px
    """
    # Проверяем токен через централизованную систему
    token_service = get_token_service()
    token_data = token_service.validate_token(token)
    
    if not token_data:
        raise HTTPException(
            status_code=401, 
            detail="Недействительный или истекший токен доступа"
        )
    
    # Валидируем параметры
    if theme not in ["light", "dark"]:
        theme = "light"
    
    if mode not in ["widget", "expanded"]:
        mode = "widget"
    
    # Получаем базовый URL как строку
    base_url = str(request.base_url).rstrip('/')
    
    import time
    timestamp = int(time.time())
    
    # Подготавливаем контекст для шаблона
    context = {
        "request": request,
        "token": token,
        "flow_id": flow_id,
        "session_id": session_id,
        "theme": theme,
        "width": width,
        "height": height,
        "user_id": user_id or token_data.user_id,
        "mode": mode,
        "token_data": token_data,
        "base_url": base_url,
        "timestamp": timestamp
    }
    
    return templates.TemplateResponse("embed_chat.html", context)


@router.get("/demo", response_class=HTMLResponse)
async def embed_demo(request: Request):
    """
    Демо-страница встраивания чата
    
    Показывает примеры кода для встраивания чата в различные сайты
    """
    # Получаем токен из куки (пользователь должен быть авторизован)
    token = request.cookies.get("auth_token")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Проверяем токен
    token_service = get_token_service()
    token_data = token_service.validate_token(token)
    
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    
    # Создаем демо-токен для встраивания
    embed_token = token_service.create_token(
        user_id=token_data.user_id,
        company_id=token_data.company_id,
        session_id=token_data.session_id,
        expires_in=86400,  # 1 день
        metadata={"flow_id": "demo_flow", "embed": True, "demo": True}
    )
    
    # Формируем URL для встраивания
    embed_url = f"/frontend/chat/embed?token={embed_token}&flow_id=demo_flow"
    
    context = {
        "request": request,
        "token": embed_token,
        "flow_id": "demo_flow",
        "embed_url": embed_url
    }
    
    return templates.TemplateResponse("embed_demo.html", context)


@router.post("/create-embed-token")
async def create_embed_token(
    request: Request,
    flow_id: str = Query(..., description="ID flow для чата"),
    expires_in: int = Query(86400, description="Время жизни токена в секундах"),
    user_id: Optional[str] = Query(None, description="ID пользователя"),
    company_id: Optional[str] = Query(None, description="ID компании")
):
    """
    Создает токен для встраивания чата
    
    Этот endpoint доступен только авторизованным пользователям.
    Создает токен типа EMBED для встраивания чата на внешние сайты.
    """
    # Получаем токен из куки (пользователь должен быть авторизован)
    token = request.cookies.get("session_id")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Проверяем токен пользователя
    token_service = get_token_service()
    user_token_data = token_service.validate_token(token)
    
    if not user_token_data:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    
    # Создаем токен для встраивания (тот же JWT, но с метаданными)
    embed_token = token_service.create_token(
        user_id=user_token_data.user_id,
        company_id=company_id or user_token_data.company_id,
        session_id=user_token_data.session_id,
        expires_in=expires_in,
        metadata={"flow_id": flow_id, "embed": True, "created_by": user_token_data.user_id}
    )
    
    return {
        "token": embed_token,
        "flow_id": flow_id,
        "expires_in": expires_in,
        "embed_url": f"/frontend/chat/embed?token={embed_token}&flow_id={flow_id}"
    }


@router.get("/test", response_class=HTMLResponse)
async def test_embed(request: Request):
    """
    Тестовая страница для проверки встроенного чата
    
    Позволяет протестировать встроенный чат с различными параметрами
    Доступна без авторизации для удобства тестирования
    """
    # Получаем параметры из URL
    api_url = request.query_params.get("api_url")
    token = request.query_params.get("token")
    flow_id = request.query_params.get("flow_id", "app.flows.faq_flow.faq_flow_config")
    
    # Если api_url не указан, используем текущий домен
    if not api_url:
        api_url = str(request.base_url).rstrip('/')
    
    context = {
        "request": request,
        "api_url": api_url,
        "token": token,
        "flow_id": flow_id
    }
    
    return templates.TemplateResponse("test_embed.html", context)


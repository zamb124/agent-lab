"""
Вспомогательные функции для HTMX ответов
Автоматическое обновление header на уровне core
"""
from fastapi import Request
from fastapi.responses import HTMLResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse
from app.frontend.core.template_loader import get_templates
from app.frontend.core.plugin_loader import get_plugins_for_template


templates = get_templates()


def add_header_to_htmx_response(request: Request, html_content: str) -> str:
    """Добавляет обновленный header к HTMX ответу
    
    Args:
        request: FastAPI Request объект
        html_content: HTML контент страницы
        
    Returns:
        HTML с добавленным header fragment
    """
    plugin_data = get_plugins_for_template(request)
    
    header_right_html = templates.get_template("_header_right_fragment.html").render(
        request=request,
        header_actions=plugin_data.get("header_actions", [])
    )
    
    return html_content + "\n" + header_right_html


class HTMXHeaderMiddleware(BaseHTTPMiddleware):
    """Middleware для автоматического обновления header при HTMX запросах
    
    Плагины только декларируют кнопки в header_actions.
    Этот middleware автоматически обновляет header для всех HTMX запросов.
    """
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        is_htmx = request.headers.get("HX-Request") == "true"
        is_frontend_route = request.url.path.startswith("/frontend/")
        is_html_response = response.headers.get("content-type", "").startswith("text/html")
        
        if is_htmx and is_frontend_route and is_html_response:
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            
            html_content = body.decode('utf-8')
            
            plugin_data = get_plugins_for_template(request)
            header_actions = plugin_data.get("header_actions", [])
            
            # Получаем user_companies из request.state (установлено AuthMiddleware)
            user_companies = getattr(request.state, 'user_companies', [])
            
            header_fragment = templates.get_template("_header_right_fragment.html").render(
                request=request,
                header_actions=header_actions,
                user_companies=user_companies
            )
            
            updated_html = html_content + "\n" + header_fragment
            
            new_headers = dict(response.headers)
            new_headers.pop("content-length", None)
            new_headers.pop("Content-Length", None)
            
            return HTMLResponse(
                content=updated_html,
                status_code=response.status_code,
                headers=new_headers,
            )
        
        return response


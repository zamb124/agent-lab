"""
Вспомогательные функции для HTMX ответов
Автоматическое обновление header на уровне core
"""

from fastapi import Request
from fastapi.responses import HTMLResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.frontend.template_loader import get_templates
from core.frontend.plugins.loader import get_plugins_for_template


def add_header_to_htmx_response(request: Request, html_content: str) -> str:
    """Добавляет обновленный header к HTMX ответу"""
    templates = get_templates()
    plugin_data = get_plugins_for_template(request)
    
    header_right_html = templates.get_template("_header_right_fragment.html").render(
        request=request,
        header_actions=plugin_data.get("header_actions", [])
    )
    
    return html_content + "\n" + header_right_html


class HTMXHeaderMiddleware(BaseHTTPMiddleware):
    """Middleware для автоматического обновления header при HTMX запросах"""
    
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
            
            templates = get_templates()
            plugin_data = get_plugins_for_template(request)
            header_actions = plugin_data.get("header_actions", [])
            
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


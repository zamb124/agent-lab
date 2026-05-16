"""
Chat API - веб-интерфейс для SSE чата с агентами.
"""

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from apps.flows.src.channels.a2a import A2AChannel
from apps.flows.src.container import FlowContainer
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models.flow_config import FlowConfig
from core.context import get_context
from core.frontend.viewport import PLATFORM_MOBILE_VIEWPORT_CONTENT
from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["chat"])


async def _get_flow_config(flow_id: str, container: FlowContainer) -> FlowConfig | None:
    """Получает конфигурацию агента из репозитория."""
    return await container.flow_repository.get(flow_id)


def _get_base_url(request: Request) -> str:
    """Получает базовый URL из request."""
    # Приоритет X-Forwarded-Proto над request.url.scheme
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto:
        scheme = forwarded_proto.lower()
    else:
        # Если заголовка нет, но запрос идет через SSL порт, используем https
        scheme = request.url.scheme

    # Используем X-Forwarded-Host, который содержит host:port от Nginx
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        host = forwarded_host
    else:
        host = request.headers.get("host") or request.url.netloc
        # Если host не содержит порт, добавляем порт
        if ":" not in host:
            if request.url.port:
                host = f"{host}:{request.url.port}"
            elif scheme == "https":
                host = f"{host}:443"
            elif scheme == "http":
                host = f"{host}:80"

    base_url = f"{scheme}://{host}"
    logger.info(f"Base URL: {base_url}, X-Forwarded-Proto: {forwarded_proto}, X-Forwarded-Host: {forwarded_host}, request.url.scheme: {request.url.scheme}, request.headers: {dict(request.headers)}")
    return base_url


@router.get("/{flow_id}/chat")
async def get_chat_interface(flow_id: str, request: Request, container: ContainerDep) -> HTMLResponse:
    """
    Возвращает HTML интерфейс чата для указанного агента.

    Проверяет существование агента и возвращает шаблон с настройками авторизации.
    Загружает список веток (branches) для выбора в интерфейсе.
    """
    config = await _get_flow_config(flow_id, container)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    base_url = _get_base_url(request)

    # Получаем список веток
    context = get_context()
    channel = A2AChannel(flow_id, context=context, container=container)
    branches_list = await channel.list_branches()

    # Получаем email пользователя из контекста или request.state
    user_email = ""
    if context and context.metadata:
        user_email = context.metadata.get("email", "")
    elif hasattr(request.state, "user") and request.state.user:
        user_email = request.state.user.get("email", "")

    # Путь к шаблону
    template_dir = Path(__file__).parent.parent.parent / "static"
    template_file = "chat.html"

    # Если шаблона нет в static, используем встроенный
    if not (template_dir / template_file).exists():
        # Используем встроенный шаблон
        html_content = _get_embedded_template(flow_id, base_url, branches_list)
        return HTMLResponse(content=html_content)

    # Загружаем шаблон через Jinja2
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"])
    )
    template = env.get_template(template_file)

    html_content = template.render(
        flow_id=flow_id,
        base_url=base_url,
        flow_name=config.name or flow_id,
        branches=branches_list,
        user_email=user_email,
    )

    return HTMLResponse(content=html_content)


def _get_embedded_template(flow_id: str, base_url: str, branches: list[dict[str, Any]]) -> str:
    """Возвращает встроенный HTML шаблон если файл не найден."""
    branches_json = json.dumps(branches)
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="{PLATFORM_MOBILE_VIEWPORT_CONTENT}">
    <title>Chat - {flow_id}</title>
    <style>
        /* CSS будет встроен в chat.html */
    </style>
</head>
<body>
    <div id="chat-container"></div>
    <script>
        window.CHAT_CONFIG = {{
            flowId: "{flow_id}",
            baseUrl: "{base_url}",
            branches: {branches_json}
        }};
    </script>
    <script src="/static/chat.js"></script>
</body>
</html>"""

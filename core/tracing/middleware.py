"""
TracingMiddleware для автоматического создания spans для HTTP запросов.
"""

from collections.abc import Awaitable, Callable
from typing import override

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from core.context import get_context
from core.logging import get_logger

from .provider import is_tracing_enabled
from .tracer import get_tracer

logger = get_logger(__name__)


class TracingMiddleware(BaseHTTPMiddleware):
    """
    Middleware для автоматического трейсинга HTTP запросов.

    Создает root span для каждого запроса с данными из Context.
    """

    @override
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not is_tracing_enabled():
            return await call_next(request)

        # Пропускаем health checks и статику
        path = request.url.path
        if path in ("/health", "/", "/openapi.json", "/docs", "/redoc"):
            return await call_next(request)
        if path.startswith("/static/"):
            return await call_next(request)

        tracer = get_tracer()
        context = get_context()

        # Создаем TraceContext из Context приложения
        trace_ctx = None
        if context:
            user_groups_raw = context.metadata.get("grps")
            if user_groups_raw is None:
                user_groups: list[str] = []
            elif isinstance(user_groups_raw, list) and all(
                isinstance(group, str) for group in user_groups_raw
            ):
                user_groups = [group for group in user_groups_raw if isinstance(group, str)]
            else:
                raise ValueError("context.metadata.grps must be a string array")
            trace_ctx = tracer.create_trace_context(
                user_id=context.user.user_id,
                user_name=context.user.name,
                user_groups=user_groups,
                session_auth=context.session_id,
                flow_id=context.flow_id,
                channel=context.channel,
            )

        method = f"{request.method} {path}"

        async with tracer.request_span(method=method, trace_ctx=trace_ctx) as span:
            response = await call_next(request)
            span.set_attribute("http.status_code", response.status_code)
            if response.status_code >= 400:
                span.set_attribute("error", True)
            return response

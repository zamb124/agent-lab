"""
 * @file: decorators.py
 * @description: Декораторы для записи трейсов (spans) в OTEL/БД через стандартный Tracer
 * @dependencies: opentelemetry, app.models.trace_models.SpanType, app.core.context.get_context
 * @created: 2025-10-30
"""

import json
import functools
import inspect
from typing import Any, Callable, Optional, Dict

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from apps.agents.models.trace_models import SpanType
from core.context import get_context


def _safe_serialize(value: Any, max_len: int = 4000) -> str:
    """
    Бездополнительных зависимостей сериализует значение в JSON-строку.
    Ограничивает длину, чтобы не раздувать атрибуты спана.
    """
    try:
        serialized = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        serialized = str(value)
    if len(serialized) > max_len:
        return serialized[: max_len - 3] + "..."
    return serialized


def trace_span(
    name: Optional[str] = None,
    span_type: SpanType = SpanType.AGENT,
    metadata: Optional[Dict[str, Any]] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Декоратор для записи спана вокруг вызова функции (sync/async).

    Автоматически присоединяется к активному OTEL trace context (если есть),
    создавая дочерний span. Если активного контекста нет - создаёт новый trace.

    Args:
        name: Имя спана. По умолчанию — имя функции
        span_type: Тип спана (для фронтенда и аналитики)
        metadata: Доп. метаданные, будут записаны в атрибуты спана

    Returns:
        Обёрнутая функция, создающая OTEL span с атрибутами:
        - span_type
        - input_data (json str)
        - output_data (json str)
        - context_user_id, context_company_id, context_session_id (если есть контекст)
        - произвольные meta_* из metadata
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        tracer = trace.get_tracer("agent-lab.core.tracing")
        span_name = name or func.__name__

        async def _run_async(*args: Any, **kwargs: Any) -> Any:
            # start_as_current_span автоматически использует активный span как родителя
            with tracer.start_as_current_span(span_name) as span:
                # Базовые атрибуты
                span.set_attribute("span_type", span_type.value)

                # Контекст (если доступен)
                context = get_context()
                if context and context.user:
                    span.set_attribute("context_user_id", context.user.user_id)
                if context and context.active_company:
                    span.set_attribute("context_company_id", context.active_company.company_id)
                if context and context.session_id:
                    span.set_attribute("context_session_id", context.session_id)

                # Пользовательские метаданные
                if metadata:
                    for key, value in metadata.items():
                        span.set_attribute(f"meta_{key}", _safe_serialize(value))

                # Входные данные
                span.set_attribute("input_data", _safe_serialize({"args": args, "kwargs": kwargs}))

                try:
                    result = await func(*args, **kwargs)
                    span.set_attribute("output_data", _safe_serialize(result))
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(status_code=StatusCode.ERROR, description=str(e)))
                    raise

        def _run_sync(*args: Any, **kwargs: Any) -> Any:
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("span_type", span_type.value)

                context = get_context()
                if context and context.user:
                    span.set_attribute("context_user_id", context.user.user_id)
                if context and context.active_company:
                    span.set_attribute("context_company_id", context.active_company.company_id)
                if context and context.session_id:
                    span.set_attribute("context_session_id", context.session_id)

                if metadata:
                    for key, value in metadata.items():
                        span.set_attribute(f"meta_{key}", _safe_serialize(value))

                span.set_attribute("input_data", _safe_serialize({"args": args, "kwargs": kwargs}))

                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("output_data", _safe_serialize(result))
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(status_code=StatusCode.ERROR, description=str(e)))
                    raise

        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await _run_async(*args, **kwargs)

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            return _run_sync(*args, **kwargs)

        return sync_wrapper

    return decorator



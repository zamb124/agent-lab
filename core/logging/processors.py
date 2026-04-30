"""
Структурированные процессоры structlog для платформы.

Процессоры выполняются в порядке передачи в structlog.configure(...). Каждый
получает (logger, method_name, event_dict) и возвращает event_dict (или
поднимает исключение, если запись надо отбросить — DropEvent).
"""

from __future__ import annotations

import random
from typing import Any, Callable

import structlog
from structlog.types import EventDict, WrappedLogger


def add_service_fields(service_name: str, version: str | None, environment: str) -> Callable[[WrappedLogger, str, EventDict], EventDict]:
    """Процессор-замыкание: проставляет service.name/version и deployment.environment."""

    def processor(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
        event_dict.setdefault("service.name", service_name)
        if version:
            event_dict.setdefault("service.version", version)
        event_dict.setdefault("deployment.environment", environment)
        return event_dict

    return processor


def add_otel_trace_context(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    """
    Подмешивает trace_id/span_id из текущего OpenTelemetry-спана.

    Ничего не пишет, если активного спана нет — fallback на trace_id из
    core.context делает другой процессор (add_platform_context).
    """
    try:
        from opentelemetry import trace as otel_trace
    except ImportError:
        return event_dict

    span = otel_trace.get_current_span()
    if span is None:
        return event_dict

    span_context = span.get_span_context()
    if not span_context or not span_context.is_valid:
        return event_dict

    event_dict.setdefault("trace_id", format(span_context.trace_id, "032x"))
    event_dict.setdefault("span_id", format(span_context.span_id, "016x"))
    return event_dict


def add_platform_context(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    """
    Fallback: если trace_id ещё не выставлен (нет OTel-спана) — берём из
    core.context.Context. user_id/company_id биндятся явно через
    bind_log_context в AuthMiddleware, но fallback тут оставлен для случаев,
    когда контекст уже есть, а bind ещё не выполнен (раннее логирование).
    """
    if "trace_id" in event_dict and "user_id" in event_dict and "company_id" in event_dict:
        return event_dict

    from core.context import get_context

    context = get_context()
    if context is None:
        return event_dict

    if "trace_id" not in event_dict and getattr(context, "trace_id", None):
        event_dict["trace_id"] = context.trace_id
    if "user_id" not in event_dict and context.user is not None:
        event_dict.setdefault("user_id", context.user.user_id)
    if "company_id" not in event_dict and context.active_company is not None:
        event_dict.setdefault("company_id", context.active_company.company_id)
        if context.active_company.subdomain:
            event_dict.setdefault("company_subdomain", context.active_company.subdomain)
    if "session_id" not in event_dict and getattr(context, "session_id", None):
        event_dict["session_id"] = context.session_id
    if "namespace" not in event_dict and getattr(context, "active_namespace", None) and context.active_namespace != "default":
        event_dict["namespace"] = context.active_namespace
    return event_dict


def truncate_strings(max_length: int) -> Callable[[WrappedLogger, str, EventDict], EventDict]:
    """Ограничить длину строковых значений; обрезанные помечаются `_truncated`."""

    if max_length <= 0:
        raise ValueError("max_length должен быть положительным")

    def processor(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
        truncated_keys: list[str] = []
        for key, value in list(event_dict.items()):
            if isinstance(value, str) and len(value) > max_length:
                event_dict[key] = value[:max_length]
                truncated_keys.append(key)
        if truncated_keys:
            event_dict["_truncated"] = truncated_keys
        return event_dict

    return processor


def redact_keys(drop_keys: list[str]) -> Callable[[WrappedLogger, str, EventDict], EventDict]:
    """Заменить значения указанных ключей на маркер REDACT_PLACEHOLDER."""

    if not drop_keys:
        return _passthrough

    drop_set = frozenset(drop_keys)
    from core.logging.contract import REDACT_PLACEHOLDER

    def processor(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
        for key in list(event_dict.keys()):
            if key in drop_set:
                event_dict[key] = REDACT_PLACEHOLDER
        return event_dict

    return processor


def sample_info_logs(rate: float, sampled_loggers: list[str]) -> Callable[[WrappedLogger, str, EventDict], EventDict]:
    """
    Дропнуть часть INFO-записей у hot-path логгеров.

    Применяется только если method_name == "info" и имя логгера
    начинается с одного из sampled_loggers. WARNING/ERROR/DEBUG не
    дропаются никогда.
    """

    if rate >= 1.0 or not sampled_loggers:
        return _passthrough

    if rate < 0.0:
        raise ValueError("sample_rate_info должен быть >= 0")

    sampled_prefixes = tuple(sampled_loggers)

    def processor(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
        if method_name != "info":
            return event_dict
        logger_name = event_dict.get("logger", "") or getattr(logger, "name", "")
        if not isinstance(logger_name, str) or not logger_name.startswith(sampled_prefixes):
            return event_dict
        if random.random() >= rate:
            raise structlog.DropEvent
        return event_dict

    return processor


def rename_event_to_message(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    """
    structlog по умолчанию кладёт первую позицию в "event"; мы хотим, чтобы
    в JSON это было "message". Если уже задано "event" пользователем —
    переносим его в отдельный ключ "event_name".
    """
    if "event" in event_dict and "message" not in event_dict:
        event_dict["message"] = event_dict.pop("event")
    return event_dict


def _passthrough(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    return event_dict


def add_log_level_uppercase(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    """Приводит ключ level к UPPER (стандарт OTel logs)."""
    level = event_dict.get("level")
    if isinstance(level, str):
        event_dict["level"] = level.upper()
    return event_dict


def remove_internal_keys(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    """Удаляет служебные ключи structlog (positional_args), которые не нужны в выводе."""
    event_dict.pop("positional_args", None)
    event_dict.pop("_record", None)
    event_dict.pop("_from_structlog", None)
    return event_dict


def enforce_required_fields(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
    """
    Гарантирует контракт обязательных полей записи в request-скоупе.

    Поведение:
    - В system-скоупе требует только `service.name` (всегда есть от
      add_service_fields).
    - В request-скоупе требует `request_id`, `trace_id`, `service.name`.
    - Если scope помечен как `requires_user=True`, дополнительно требует
      `user_id` и `company_id`.

    При нарушении контракта запись **не уходит в stdout** (raise DropEvent).
    Вместо неё печатается отдельная аварийная запись напрямую в stderr
    через изолированный `_emit_contract_violation`, минуя весь pipeline.

    Это самый последний слой защиты канона: настоящие точки правки —
    middleware/handler/scheduler/background, которые обязаны входить в
    request-скоуп через core.logging.scope.enter_request_scope(...).
    """
    import structlog

    from core.logging.scope import (
        REQUIRED_AUTHENTICATED_REQUEST_KEYS,
        REQUIRED_REQUEST_KEYS,
        get_log_scope,
        get_log_scope_requires_user,
    )

    if "service.name" not in event_dict:
        _emit_contract_violation(
            event_dict,
            missing=("service.name",),
            scope="any",
        )
        raise structlog.DropEvent

    if get_log_scope() != "request":
        return event_dict

    missing = [key for key in REQUIRED_REQUEST_KEYS if not _has_field(event_dict, key)]

    if get_log_scope_requires_user():
        missing.extend(
            key for key in REQUIRED_AUTHENTICATED_REQUEST_KEYS if not _has_field(event_dict, key)
        )

    if missing:
        _emit_contract_violation(
            event_dict,
            missing=tuple(missing),
            scope="request",
        )
        raise structlog.DropEvent

    return event_dict


def _has_field(event_dict: EventDict, key: str) -> bool:
    value = event_dict.get(key)
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _emit_contract_violation(
    event_dict: EventDict,
    *,
    missing: tuple[str, ...],
    scope: str,
) -> None:
    """
    Пишет аварийную запись о нарушении контракта напрямую в stderr.

    Не использует stdlib logging вообще, чтобы не уйти в петлю с
    enforce_required_fields. Этот лог — диагностический; реальные ERROR
    остаются в логах после правки причины (точки входа без request scope).
    """
    import json
    import sys

    payload = {
        "level": "ERROR",
        "logger": "platform.logging.contract",
        "message": "logging.contract_violation",
        "scope": scope,
        "missing_fields": list(missing),
        "violating_logger": event_dict.get("logger"),
        "violating_event": event_dict.get("event") or event_dict.get("message"),
    }
    try:
        sys.stderr.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stderr.flush()
    except Exception:
        # Никаких фолбеков на скрытие ошибок: stderr недоступен — процесс
        # бесполезен, но писать в random handler нельзя (петля).
        pass

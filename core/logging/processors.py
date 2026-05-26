"""
Структурированные процессоры structlog для платформы.

Процессоры выполняются в порядке передачи в structlog.configure(...). Каждый
получает (logger, method_name, event_dict) и возвращает event_dict (или
поднимает исключение, если запись надо отбросить — DropEvent).
"""

from __future__ import annotations

import json
import random
import sys
import zlib
from collections.abc import Callable, MutableMapping
from typing import Protocol, TypeAlias

import structlog
from opentelemetry import trace as otel_trace

from core.context import get_context
from core.logging.contract import REDACT_PLACEHOLDER
from core.logging.scope import (
    REQUIRED_AUTHENTICATED_REQUEST_KEYS,
    REQUIRED_REQUEST_KEYS,
    get_log_scope,
    get_log_scope_requires_user,
)
from core.types import JsonValue


class LogProcessorLogger(Protocol):
    name: str


LogEvent: TypeAlias = MutableMapping[str, JsonValue]
LogProcessor: TypeAlias = Callable[[LogProcessorLogger, str, LogEvent], LogEvent]


def add_service_fields(service_name: str, version: str | None, environment: str) -> LogProcessor:
    """Процессор-замыкание: проставляет service.name/version и deployment.environment."""

    def processor(_logger: LogProcessorLogger, _method: str, event_dict: LogEvent) -> LogEvent:
        if "service.name" not in event_dict:
            event_dict["service.name"] = service_name
        if version and "service.version" not in event_dict:
            event_dict["service.version"] = version
        if "deployment.environment" not in event_dict:
            event_dict["deployment.environment"] = environment
        return event_dict

    return processor


def add_otel_trace_context(
    _logger: LogProcessorLogger,
    _method: str,
    event_dict: LogEvent,
) -> LogEvent:
    """
    Подмешивает trace_id/span_id из текущего OpenTelemetry-спана.

    Ничего не пишет, если активного спана нет. Платформенный Context
    добавляется отдельным процессором add_platform_context.
    """
    span = otel_trace.get_current_span()
    span_context = span.get_span_context()
    if not span_context.is_valid:
        return event_dict

    if "trace_id" not in event_dict:
        event_dict["trace_id"] = format(span_context.trace_id, "032x")
    if "span_id" not in event_dict:
        event_dict["span_id"] = format(span_context.span_id, "016x")
    return event_dict


def add_platform_context(
    _logger: LogProcessorLogger,
    _method: str,
    event_dict: LogEvent,
) -> LogEvent:
    """
    Добавляет поля из core.context.Context, когда они ещё не были забинжены
    request-scope middleware.
    """
    if "trace_id" in event_dict and "user_id" in event_dict and "company_id" in event_dict:
        return event_dict

    context = get_context()
    if context is None:
        return event_dict

    if "trace_id" not in event_dict and context.trace_id:
        event_dict["trace_id"] = context.trace_id
    if "user_id" not in event_dict:
        event_dict["user_id"] = context.user.user_id
    if "company_id" not in event_dict and context.active_company is not None:
        event_dict["company_id"] = context.active_company.company_id
        if context.active_company.subdomain:
            event_dict["company_subdomain"] = context.active_company.subdomain
    if "session_id" not in event_dict and context.session_id:
        event_dict["session_id"] = context.session_id
    if (
        "namespace" not in event_dict
        and context.active_namespace
        and context.active_namespace != "default"
    ):
        event_dict["namespace"] = context.active_namespace
    return event_dict


def truncate_strings(max_length: int) -> LogProcessor:
    """Ограничить длину строковых значений; обрезанные помечаются `_truncated`."""

    if max_length <= 0:
        raise ValueError("max_length должен быть положительным")

    def processor(_logger: LogProcessorLogger, _method: str, event_dict: LogEvent) -> LogEvent:
        truncated_keys: list[str] = []
        for key, value in list(event_dict.items()):
            if isinstance(value, str) and len(value) > max_length:
                event_dict[key] = value[:max_length]
                truncated_keys.append(key)
        if truncated_keys:
            event_dict["_truncated"] = truncated_keys
        return event_dict

    return processor


def redact_keys(drop_keys: list[str]) -> LogProcessor:
    """Заменить значения указанных ключей на маркер REDACT_PLACEHOLDER."""

    if not drop_keys:
        return _passthrough

    drop_set = frozenset(drop_keys)

    def processor(_logger: LogProcessorLogger, _method: str, event_dict: LogEvent) -> LogEvent:
        for key in list(event_dict.keys()):
            if key in drop_set:
                event_dict[key] = REDACT_PLACEHOLDER
        return event_dict

    return processor


def _should_sample(trace_id: str, rate: float) -> bool:
    if rate >= 1.0:
        return True
    h = zlib.crc32(trace_id.encode("utf-8")) & 0xFFFFFFFF
    return h < rate * (2**32)


def sample_info_logs(rate: float, sampled_loggers: list[str]) -> LogProcessor:
    """
    Дропнуть часть INFO-записей у hot-path логгеров.

    Применяется только если method_name == "info" и имя логгера
    начинается с одного из sampled_loggers. WARNING/ERROR/DEBUG не
    дропаются никогда.

    Sampling детерминированный: решение принимается на основе trace_id.
    Весь трейс либо логируется полностью, либо дропается целиком —
    это стандартная практика observability, избегает «дырявых» трейсов.
    """

    if rate >= 1.0 or not sampled_loggers:
        return _passthrough

    if rate < 0.0:
        raise ValueError("sample_rate_info должен быть >= 0")

    sampled_prefixes = tuple(sampled_loggers)

    def processor(
        logger: LogProcessorLogger,
        method_name: str,
        event_dict: LogEvent,
    ) -> LogEvent:
        if method_name != "info":
            return event_dict
        logger_name_raw = event_dict.get("logger")
        logger_name = logger_name_raw if isinstance(logger_name_raw, str) else logger.name
        if not logger_name.startswith(sampled_prefixes):
            return event_dict
        trace_id = event_dict.get("trace_id")
        if isinstance(trace_id, str) and trace_id.strip():
            if not _should_sample(trace_id, rate):
                raise structlog.DropEvent
            return event_dict
        # trace_id отсутствует — используем random как резерв, чтобы не потерять запись совсем
        if random.random() >= rate:
            raise structlog.DropEvent
        return event_dict

    return processor


def rename_event_to_message(
    _logger: LogProcessorLogger,
    _method: str,
    event_dict: LogEvent,
) -> LogEvent:
    """
    structlog по умолчанию кладёт первую позицию в "event"; мы хотим, чтобы
    в JSON это было "message". Если уже задано "event" пользователем —
    переносим его в отдельный ключ "event_name".
    """
    if "event" in event_dict and "message" not in event_dict:
        event_dict["message"] = event_dict.pop("event")
    return event_dict


def _passthrough(_logger: LogProcessorLogger, _method: str, event_dict: LogEvent) -> LogEvent:
    return event_dict


def add_log_level_uppercase(
    _logger: LogProcessorLogger,
    _method: str,
    event_dict: LogEvent,
) -> LogEvent:
    """Приводит ключ level к UPPER (стандарт OTel logs)."""
    level = event_dict.get("level")
    if isinstance(level, str):
        event_dict["level"] = level.upper()
    return event_dict


def remove_internal_keys(
    _logger: LogProcessorLogger,
    _method: str,
    event_dict: LogEvent,
) -> LogEvent:
    """Удаляет служебные ключи structlog (positional_args), которые не нужны в выводе."""
    _ = event_dict.pop("positional_args", None)
    _ = event_dict.pop("_record", None)
    _ = event_dict.pop("_from_structlog", None)
    return event_dict


def enforce_required_fields(
    _logger: LogProcessorLogger,
    _method: str,
    event_dict: LogEvent,
) -> LogEvent:
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


def _has_field(event_dict: LogEvent, key: str) -> bool:
    value = event_dict.get(key)
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _emit_contract_violation(
    event_dict: LogEvent,
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
    payload = {
        "level": "ERROR",
        "logger": "platform.logging.contract",
        "message": "logging.contract_violation",
        "scope": scope,
        "missing_fields": list(missing),
        "violating_logger": event_dict.get("logger"),
        "violating_event": event_dict.get("event") or event_dict.get("message"),
    }
    _ = sys.stderr.write(json.dumps(payload, ensure_ascii=False) + "\n")
    _ = sys.stderr.flush()

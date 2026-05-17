"""
Идемпотентная инициализация логирования платформы.

Подход:
- structlog держит pipeline процессоров и формирует event_dict.
- ProcessorFormatter рендерит итоговую запись (JSON или console).
- stdlib logging — единственный транспорт; root логгер пишет в stdout.
- uvicorn/taskiq логгеры теряют свои handlers и пропагируют в root.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Optional

import structlog

from core.config import get_settings
from core.config.testing import is_testing
from core.logging.contract import LoggingMisconfigured
from core.logging.loki_handler import LokiHandler
from core.logging.processors import (
    add_log_level_uppercase,
    add_otel_trace_context,
    add_platform_context,
    add_service_fields,
    enforce_required_fields,
    redact_keys,
    remove_internal_keys,
    rename_event_to_message,
    sample_info_logs,
    truncate_strings,
)

_initialized = False
_initialized_for: tuple[str, str] | None = None


def _resolve_environment() -> str:
    """local / test / production по ENV."""
    if is_testing():
        return "test"
    env = (
        _safe_env("PLATFORM_ENV")
        or _safe_env("DEPLOYMENT_ENV")
        or _safe_env("ENV")
    )
    if env:
        env_lower = env.lower()
        if env_lower in {"local", "test", "production"}:
            return env_lower
    if _safe_env("DEPLOYMENT_VERSION") or _safe_env("SERVER__DEPLOYMENT_VERSION"):
        return "production"
    return "local"


def _safe_env(name: str) -> str:
    value = os.environ.get(name)
    return value.strip() if isinstance(value, str) else ""


def _build_processors_chain(
    *,
    service_name: str,
    service_version: Optional[str],
    environment: str,
    sample_rate_info: float,
    sampled_loggers: list[str],
    drop_keys: list[str],
    max_string_len: int,
    is_console: bool,
) -> list[Any]:
    """Список processors для structlog.configure (для structlog API)."""
    chain: list[Any] = [
        structlog.contextvars.merge_contextvars,
        add_service_fields(service_name, service_version, environment),
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        add_log_level_uppercase,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        add_otel_trace_context,
        add_platform_context,
        sample_info_logs(sample_rate_info, sampled_loggers),
        enforce_required_fields,
        truncate_strings(max_string_len),
        redact_keys(drop_keys),
        rename_event_to_message,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        remove_internal_keys,
    ]
    chain.append(structlog.stdlib.ProcessorFormatter.wrap_for_formatter)
    return chain


def _build_renderer(format_name: str, console_colors: bool) -> Any:
    if format_name == "json":
        return structlog.processors.JSONRenderer(
            sort_keys=False,
            serializer=lambda obj, **kwargs: json.dumps(obj, ensure_ascii=False, **kwargs),
        )
    if format_name == "console":
        return structlog.dev.ConsoleRenderer(colors=console_colors)
    raise LoggingMisconfigured(
        f"Неизвестный формат логирования: {format_name!r}. Допустимо: 'json' | 'console'."
    )


def _build_foreign_pre_chain(
    service_name: str,
    service_version: Optional[str],
    environment: str,
) -> list[Any]:
    """
    Pre-chain для записей из stdlib (uvicorn, taskiq, sqlalchemy и т.п.):
    добавляем те же контекстные поля, что и для structlog, чтобы вывод
    был однородным.
    """
    return [
        structlog.contextvars.merge_contextvars,
        add_service_fields(service_name, service_version, environment),
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        add_log_level_uppercase,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        add_otel_trace_context,
        add_platform_context,
        enforce_required_fields,
    ]


def setup_logging(service_name: str, logging_config=None) -> None:
    """
    Идемпотентно настраивает логирование процесса.

    Повторный вызов с тем же service_name/format не делает ничего.
    Повторный вызов с другими параметрами поднимает LoggingMisconfigured —
    это запрет менять формат на лету (тестовая инфраструктура должна
    инициализировать раз).
    """
    global _initialized, _initialized_for

    if logging_config is None:
        logging_config = get_settings().logging

    format_name = logging_config.format
    if format_name not in ("json", "console"):
        raise LoggingMisconfigured(
            f"logging.format должен быть 'json' | 'console', получен {format_name!r}"
        )

    level_name = logging_config.level.upper()
    if not hasattr(logging, level_name):
        raise LoggingMisconfigured(f"logging.level некорректен: {logging_config.level!r}")

    if _initialized:
        if _initialized_for == (service_name, format_name):
            return
        if os.getenv("TESTING") == "true" or "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules:
            return
        raise LoggingMisconfigured(
            "setup_logging уже вызывался с другими параметрами: "
            f"было {_initialized_for}, повторно {(service_name, format_name)}. "
            "Инициализируйте логирование один раз на процесс."
        )

    environment = _resolve_environment()
    service_version = _resolve_service_version()
    sample_rate_info = float(getattr(logging_config, "sample_rate_info", 1.0))
    sampled_loggers = list(getattr(logging_config, "sampled_loggers", []))
    drop_keys = list(getattr(logging_config, "drop_keys", []))
    max_string_len = int(getattr(logging_config, "max_string_len", 8192))
    console_colors = bool(getattr(logging_config, "console_colors", False))

    renderer = _build_renderer(format_name, console_colors)
    foreign_pre_chain = _build_foreign_pre_chain(service_name, service_version, environment)

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=foreign_pre_chain,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.setLevel(level_name)

    root_logger = logging.getLogger()
    for existing in list(root_logger.handlers):
        root_logger.removeHandler(existing)
    root_logger.addHandler(handler)

    # Loki push handler: включается явно через loki_enabled в конфиге.
    # В production/test сервисы в Docker — Alloy собирает stdout, дублировать не нужно.
    loki_url = getattr(logging_config, "loki_url", None)
    loki_enabled = getattr(logging_config, "loki_enabled", False)
    if loki_url and loki_enabled:
        loki_renderer = structlog.processors.JSONRenderer(
            sort_keys=False,
            serializer=lambda obj, **kw: json.dumps(obj, ensure_ascii=False, **kw),
        )
        loki_formatter = structlog.stdlib.ProcessorFormatter(
            processor=loki_renderer,
            foreign_pre_chain=foreign_pre_chain,
        )
        loki_handler = LokiHandler(loki_url=loki_url, service_name=service_name)
        loki_handler.setFormatter(loki_formatter)
        loki_handler.setLevel(level_name)
        root_logger.addHandler(loki_handler)

    root_logger.setLevel(level_name)

    _silence_noisy_loggers(logging_config.loggers_levels)

    structlog.configure(
        processors=_build_processors_chain(
            service_name=service_name,
            service_version=service_version,
            environment=environment,
            sample_rate_info=sample_rate_info,
            sampled_loggers=sampled_loggers,
            drop_keys=drop_keys,
            max_string_len=max_string_len,
            is_console=(format_name == "console"),
        ),
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level_name)),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _initialized = True
    _initialized_for = (service_name, format_name)


def _resolve_service_version() -> Optional[str]:
    settings = get_settings()
    server = getattr(settings, "server", None)
    if server is None:
        return None
    version = getattr(server, "deployment_version", None)
    if isinstance(version, str) and version.strip():
        return version.strip()
    return None


def _silence_noisy_loggers(custom_levels: dict[str, str]) -> None:
    """
    Уравнивает обработку чужих логгеров: handlers сбрасываются, propagate
    включается, чтобы запись попала в root и пошла через единый formatter.
    """
    intercepted = {"uvicorn", "taskiq", "httpx", "httpcore", "sqlalchemy"}
    manager = logging.Logger.manager

    for name, logger in list(manager.loggerDict.items()):
        if not any(name == p or name.startswith(f"{p}.") for p in intercepted):
            continue
        if not isinstance(logger, logging.Logger):
            continue
        logger.handlers.clear()
        logger.propagate = True

    for name in intercepted:
        child = logging.getLogger(name)
        child.handlers.clear()
        child.propagate = True

    for logger_name, level in custom_levels.items():
        target = logging.getLogger(logger_name)
        try:
            target.setLevel(level.upper())
        except (ValueError, TypeError) as exc:
            raise LoggingMisconfigured(
                f"loggers_levels[{logger_name!r}] = {level!r} некорректен"
            ) from exc


def reset_logging_for_tests() -> None:
    """Сброс состояния — только для unit-тестов фабрик."""
    global _initialized, _initialized_for
    _initialized = False
    _initialized_for = None
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

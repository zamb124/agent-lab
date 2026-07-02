"""
Идемпотентная инициализация логирования платформы.

Подход:
- structlog держит pipeline процессоров и формирует event_dict.
- ProcessorFormatter рендерит итоговую запись (JSON или console).
- stdlib logging — единственный транспорт; root логгер пишет в stdout.
- granian/taskiq логгеры теряют свои handlers и пропагируют в root.
"""

from __future__ import annotations

import logging
import os
import sys

import structlog
from structlog.types import Processor

from core.config import get_settings
from core.config.models import LoggingConfig
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
    service_version: str | None,
    environment: str,
    sample_rate_info: float,
    sampled_loggers: list[str],
    drop_keys: list[str],
    max_string_len: int,
) -> list[Processor]:
    """Список processors для structlog.configure (для structlog API)."""
    chain: list[Processor] = [
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


def _build_renderer(format_name: str, console_colors: bool) -> Processor:
    if format_name == "json":
        return structlog.processors.JSONRenderer(
            sort_keys=False,
            ensure_ascii=False,
        )
    if format_name == "console":
        return structlog.dev.ConsoleRenderer(colors=console_colors)
    raise LoggingMisconfigured(
        f"Неизвестный формат логирования: {format_name!r}. Допустимо: 'json' | 'console'."
    )


def _build_foreign_pre_chain(
    service_name: str,
    service_version: str | None,
    environment: str,
) -> list[Processor]:
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


def setup_logging(service_name: str, logging_config: LoggingConfig | None = None) -> None:
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
    level_value = logging.getLevelNamesMapping().get(level_name)
    if level_value is None:
        raise LoggingMisconfigured(f"logging.level некорректен: {logging_config.level!r}")

    if _initialized:
        if _initialized_for == (service_name, format_name):
            return
        if os.getenv("TESTING") == "true" or "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules:
            return
        raise LoggingMisconfigured(
            "setup_logging уже вызывался с другими параметрами: "
            + f"было {_initialized_for}, повторно {(service_name, format_name)}. "
            + "Инициализируйте логирование один раз на процесс."
        )

    environment = _resolve_environment()
    service_version = _resolve_service_version()
    sample_rate_info = logging_config.sample_rate_info
    sampled_loggers = list(logging_config.sampled_loggers)
    drop_keys = list(logging_config.drop_keys)
    max_string_len = logging_config.max_string_len
    console_colors = logging_config.console_colors

    renderer = _build_renderer(format_name, console_colors)
    foreign_pre_chain = _build_foreign_pre_chain(service_name, service_version, environment)

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=foreign_pre_chain,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.setLevel(level_value)

    root_logger = logging.getLogger()
    for existing in list(root_logger.handlers):
        root_logger.removeHandler(existing)
    root_logger.addHandler(handler)

    # Loki push handler: включается явно через loki_enabled в конфиге.
    # В production/test сервисы в Docker — Alloy собирает stdout, дублировать не нужно.
    loki_url = logging_config.loki_url
    loki_enabled = logging_config.loki_enabled
    if loki_url and loki_enabled:
        loki_renderer = structlog.processors.JSONRenderer(
            sort_keys=False,
            ensure_ascii=False,
        )
        loki_formatter = structlog.stdlib.ProcessorFormatter(
            processor=loki_renderer,
            foreign_pre_chain=foreign_pre_chain,
        )
        loki_handler = LokiHandler(loki_url=loki_url, service_name=service_name)
        loki_handler.setFormatter(loki_formatter)
        loki_handler.setLevel(level_value)
        root_logger.addHandler(loki_handler)

    root_logger.setLevel(level_value)

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
        ),
        wrapper_class=structlog.make_filtering_bound_logger(level_value),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _initialized = True
    _initialized_for = (service_name, format_name)


def _resolve_service_version() -> str | None:
    settings = get_settings()
    version = settings.server.deployment_version
    if isinstance(version, str) and version.strip():
        return version.strip()
    return None


def _silence_noisy_loggers(custom_levels: dict[str, str]) -> None:
    """
    Уравнивает обработку чужих логгеров: handlers сбрасываются, propagate
    включается, чтобы запись попала в root и пошла через единый formatter.
    """
    intercepted = {"granian", "_granian", "taskiq", "httpx", "httpcore", "sqlalchemy", "trafilatura"}
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

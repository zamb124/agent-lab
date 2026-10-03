"""
Инициализация OpenTelemetry TracerProvider.
"""

import atexit
import sys

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from core.config.models import TracingConfig
from core.logging import get_logger

logger = get_logger(__name__)

_initialized: bool = False
_tracer_provider: TracerProvider | None = None
_shutdown_registered: bool = False
_otlp_configured: bool = False


def _tracing_resource(service_name: str) -> Resource:
    return Resource.create(
        {
            "service.name": service_name,
            "service.version": "0.1.0",
        }
    )


def ensure_tracer_provider(service_name: str = "platform") -> TracerProvider:
    """Возвращает SDK TracerProvider для platform spans, даже без экспортёров."""
    global _tracer_provider

    if _tracer_provider is None:
        _tracer_provider = TracerProvider(resource=_tracing_resource(service_name))
        trace.set_tracer_provider(_tracer_provider)
    return _tracer_provider


def _otlp_export_endpoint(config: TracingConfig) -> str:
    """Адрес OTLP: явный otlp_endpoint, иначе tempo_endpoint при tempo_enabled."""
    configured = config.otlp_endpoint.strip()
    if configured != "":
        return configured
    if not config.tempo_enabled:
        return ""
    return config.tempo_endpoint.strip()


def setup_tracing(config: TracingConfig) -> None:
    """
    Инициализирует OpenTelemetry трейсинг.

    Аргументы:
        config: Конфигурация трейсинга
    """
    global _initialized, _shutdown_registered, _otlp_configured

    if _initialized:
        return

    if not config.enabled:
        _ = ensure_tracer_provider(config.service_name)
        logger.info("tracing.export.disabled.sdk.spans")
        return

    tracer_provider = ensure_tracer_provider(config.service_name)

    endpoint = _otlp_export_endpoint(config)
    if endpoint != "" and not _otlp_configured:
        try:
            otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
            tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            _otlp_configured = True
            logger.info("tracing.otlp_configured", endpoint=endpoint)
        except Exception as e:
            logger.warning("tracing.otlp_failed", error=str(e))

    _initialized = True
    if not _shutdown_registered:
        _ = atexit.register(shutdown_tracing)
        _shutdown_registered = True
    logger.info("trace.initialized", service=config.service_name, sampling=config.sampling_rate)


def _report_tracing_shutdown_failure(step: str, exc: BaseException) -> None:
    _ = sys.stderr.write(
        "[tracing] shutdown " + step + " failed: " + type(exc).__name__ + ": " + str(exc) + "\n"
    )


def shutdown_tracing() -> None:
    """Останавливает OTel processors. Ошибка flush или shutdown пишется в stderr: logger на atexit уже может быть закрыт."""
    global _initialized, _tracer_provider, _otlp_configured

    provider = _tracer_provider
    _initialized = False
    _tracer_provider = None
    _otlp_configured = False
    if provider is None:
        return

    try:
        _ = provider.force_flush(timeout_millis=1000)
    except Exception as exc:
        _report_tracing_shutdown_failure("force_flush", exc)
    try:
        _ = provider.shutdown()
    except Exception as exc:
        _report_tracing_shutdown_failure("shutdown", exc)


def get_tracer_provider() -> TracerProvider | None:
    """Возвращает TracerProvider или None если не инициализирован."""
    return _tracer_provider


def is_tracing_enabled() -> bool:
    """Проверяет, включен ли трейсинг."""
    return _initialized


def set_tracing_enabled(enabled: bool) -> None:
    """
    Принудительно включает/отключает трейсинг.
    Используется в тестах.
    """
    global _initialized
    _initialized = enabled

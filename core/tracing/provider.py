"""
Инициализация OpenTelemetry TracerProvider.
"""

import atexit
import os
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from core.logging import get_logger

if TYPE_CHECKING:
    from .config import TracingConfig

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
    """Returns an SDK TracerProvider for platform spans, even without exporters."""
    global _tracer_provider

    if _tracer_provider is None:
        _tracer_provider = TracerProvider(resource=_tracing_resource(service_name))
        trace.set_tracer_provider(_tracer_provider)
    return _tracer_provider


def setup_tracing(config: "TracingConfig") -> None:
    """
    Инициализирует OpenTelemetry трейсинг.

    Args:
        config: Конфигурация трейсинга
    """
    global _initialized, _shutdown_registered, _otlp_configured

    if _initialized:
        return

    if not config.enabled:
        _ = ensure_tracer_provider(config.service_name)
        logger.info("Tracing export disabled; SDK spans remain available")
        return

    tracer_provider = ensure_tracer_provider(config.service_name)

    # OTLP exporter: из ENV (docker-compose задаёт OTEL_EXPORTER_OTLP_ENDPOINT)
    # или из config.tempo_enabled/tempo_endpoint. Сервисы не трогаем —
    # достаточно одной ENV-переменной в compose для отправки трейсов в Alloy → Tempo.
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if (otlp_endpoint or config.tempo_enabled) and not _otlp_configured:
        endpoint = otlp_endpoint or config.tempo_endpoint
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
    logger.info(f"Tracing initialized: service={config.service_name}, sampling={config.sampling_rate}")


def shutdown_tracing() -> None:
    """Останавливает OTel processors/exporters без логирования из atexit/pytest teardown."""
    global _initialized, _tracer_provider, _otlp_configured

    provider = _tracer_provider
    _initialized = False
    _tracer_provider = None
    _otlp_configured = False
    if provider is None:
        return

    try:
        _ = provider.force_flush(timeout_millis=1000)
    except Exception:
        pass
    try:
        _ = provider.shutdown()
    except Exception:
        pass


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

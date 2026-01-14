"""
Инициализация OpenTelemetry TracerProvider.
"""

from typing import TYPE_CHECKING, Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from core.logging import get_logger

if TYPE_CHECKING:
    from .config import TracingConfig

logger = get_logger(__name__)

_initialized: bool = False
_tracer_provider: Optional[TracerProvider] = None


def setup_tracing(config: "TracingConfig") -> None:
    """
    Инициализирует OpenTelemetry трейсинг.
    
    Args:
        config: Конфигурация трейсинга
    """
    global _initialized, _tracer_provider

    if _initialized:
        return

    if not config.enabled:
        logger.info("Tracing disabled")
        return

    resource = Resource.create(
        {
            "service.name": config.service_name,
            "service.version": "0.1.0",
        }
    )

    _tracer_provider = TracerProvider(resource=resource)

    # Tempo exporter (OTLP)
    if config.tempo_enabled:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            otlp_exporter = OTLPSpanExporter(endpoint=config.tempo_endpoint, insecure=True)
            _tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info(f"Tracing: OTLP exporter configured for {config.tempo_endpoint}")
        except Exception as e:
            logger.warning(f"Tracing: Failed to configure OTLP exporter: {e}")

    trace.set_tracer_provider(_tracer_provider)
    _initialized = True
    logger.info(f"Tracing initialized: service={config.service_name}, sampling={config.sampling_rate}")


def get_tracer_provider() -> Optional[TracerProvider]:
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


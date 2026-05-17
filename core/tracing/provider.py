"""
Инициализация OpenTelemetry TracerProvider.
"""

import os
from typing import TYPE_CHECKING, Optional

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

    # OTLP exporter: из ENV (docker-compose задаёт OTEL_EXPORTER_OTLP_ENDPOINT)
    # или из config.tempo_enabled/tempo_endpoint. Сервисы не трогаем —
    # достаточно одной ENV-переменной в compose для отправки трейсов в Alloy → Tempo.
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint or config.tempo_enabled:
        endpoint = otlp_endpoint or config.tempo_endpoint
        try:
            otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
            _tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info("tracing.otlp_configured", endpoint=endpoint)
        except Exception as e:
            logger.warning("tracing.otlp_failed", error=str(e))

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

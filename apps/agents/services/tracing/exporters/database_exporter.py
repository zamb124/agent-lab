"""
DatabaseSpanExporter - стандартный OpenTelemetry exporter для сохранения spans в БД.

Реализует стандартный интерфейс SpanExporter из OpenTelemetry SDK.
Сохраняет spans в Redis/PostgreSQL через Storage с минимальной обработкой.
"""

import logging
import asyncio
import json
from typing import Sequence, Set, Any, Optional
from datetime import datetime, timezone

from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult, ReadableSpan
from opentelemetry.trace import StatusCode

from apps.agents.models.trace_models import SpanRecord, SpanType, SpanStatus
from apps.agents.container import get_agents_container
from core.context import set_context, get_context
from apps.agents.models.context_models import Context
from core.models.identity_models import User, Company

logger = logging.getLogger(__name__)


class DatabaseSpanExporter(SpanExporter):
    """
    Стандартный OpenTelemetry SpanExporter для сохранения в БД.

    Следует спецификации OpenTelemetry:
    https://opentelemetry.io/docs/specs/otel/trace/sdk/#span-exporter

    Преимущества:
    - Стандартный интерфейс OpenTelemetry
    - Локальное хранение в БД
    - Быстрый доступ к данным
    - Совместимость с OpenTelemetry ecosystem
    """

    def __init__(self, main_loop: Optional[asyncio.AbstractEventLoop] = None):
        """
        Инициализирует exporter.

        Storage получается из контейнера для поддержки DI.

        Args:
            main_loop: Главный event loop для запуска задач из других потоков.
                      Если None, будет определен автоматически при первом использовании.
        """
        self._background_tasks: Set[asyncio.Task] = set()
        logger.info("✅ DatabaseSpanExporter инициализирован")

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """
        Экспортирует spans в БД.

        Это синхронный метод согласно спецификации OpenTelemetry.
        Может вызываться из разных потоков, поэтому использует
        get_or_create_loop() для получения доступного event loop.

        Args:
            spans: Последовательность spans для экспорта

        Returns:
            SpanExportResult.SUCCESS
        """


        # Определяем, можем ли мы использовать create_task (если мы в том же потоке)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            raise

        for span in spans:

            # Используем create_task если мы в том же потоке где запущен loop
            task = loop.create_task(self._export_span(span))
            self._background_tasks.add(task)
            task.add_done_callback(lambda _: self._background_tasks.discard(task))


        logger.debug(f"✅ Экспортировано {len(spans)} spans в БД (fire-and-forget)")
        return SpanExportResult.SUCCESS

    async def _export_span(self, otel_span: ReadableSpan):
        """
        Сохраняет один span в БД.

        Конвертирует OpenTelemetry ReadableSpan в SpanRecord
        и сохраняет через Storage.

        Args:
            otel_span: OpenTelemetry span для сохранения
        """
        # Извлекаем attributes один раз
        attributes = dict(otel_span.attributes or {})

        # Если контекста нет, пытаемся восстановить его из атрибутов span
        if not get_context():
            company_id = attributes.get("context_company_id") or attributes.get("company_id")
            user_id = attributes.get("context_user_id") or attributes.get("user_id")

            if company_id:
                # Создаём минимальный контекст с company
                restored_context = Context(
                    user=User(
                        user_id=user_id or "system",
                        name="System",
                        companies={},
                        active_company_id=company_id
                    ),
                    active_company=Company(
                        company_id=company_id,
                        name="Unknown",
                        subdomain="unknown"
                    ),
                    session_id=attributes.get("context_session_id") or attributes.get("session_id"),
                    platform=attributes.get("platform", "system")
                )
                set_context(restored_context)
                logger.debug(
                    f"✅ Контекст восстановлен из span атрибутов: company_id={company_id}, "
                    f"user_id={user_id or 'system'}"
                )

        # Конвертируем IDs в hex формат
        span_id = format(otel_span.context.span_id, '016x')
        trace_id = format(otel_span.context.trace_id, '032x')

        # Определяем тип span
        span_type_str = attributes.get("span_type", "agent")
        try:
            span_type = SpanType(span_type_str)
        except ValueError:
            logger.warning(f"Неизвестный span_type '{span_type_str}', используется AGENT")
            span_type = SpanType.AGENT

        # Конвертируем статус
        status = SpanStatus.SUCCESS
        error = None
        if otel_span.status.status_code == StatusCode.ERROR:
            status = SpanStatus.ERROR
            error = otel_span.status.description

        # Извлекаем базовые данные из attributes
        input_data = self._parse_json_attribute(attributes.get("input_data"))
        output_data = self._parse_json_attribute(attributes.get("output_data"))
        cost = self._parse_json_attribute(attributes.get("cost"))
        usage = self._parse_json_attribute(attributes.get("usage"))

        # Все остальные attributes складываем в metadata как есть
        metadata = {k: v for k, v in attributes.items()
                   if k not in ("span_type", "input_data", "output_data", "cost", "usage")}

        # Конвертируем timestamps (OpenTelemetry использует наносекунды)
        start_time = datetime.fromtimestamp(otel_span.start_time / 1e9, tz=timezone.utc)

        end_time = None
        duration_ms = None
        if otel_span.end_time:
            end_time = datetime.fromtimestamp(otel_span.end_time / 1e9, tz=timezone.utc)
            duration_ms = (otel_span.end_time - otel_span.start_time) / 1e6

        # Parent span ID
        parent_span_id = None
        if otel_span.parent:
            parent_span_id = format(otel_span.parent.span_id, '016x')

        # Создаем SpanRecord
        span_record = SpanRecord(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            name=otel_span.name,
            span_type=span_type,
            status=status,
            start_time=start_time,
            end_time=end_time,
            duration_ms=duration_ms,
            input_data=input_data,
            output_data=output_data,
            metadata=metadata,
            cost=cost,
            usage=usage,
            error=error,
        )
        storage = get_agents_container().storage
        await storage.set(f"otel:{trace_id}:span:{span_id}", span_record.model_dump_json())

        logger.debug(f"📝 Сохранен span: {span_id} ({otel_span.name})")

    def _parse_json_attribute(self, value: Any) -> Any:
        """
        Парсит JSON из attribute.

        OpenTelemetry сериализует сложные типы (dict, list) в JSON строки.
        Этот метод пытается десериализовать их обратно.

        Args:
            value: Значение attribute

        Returns:
            Десериализованное значение или исходное значение
        """
        if value is None:
            return None

        # Если уже dict/list - возвращаем как есть
        if isinstance(value, (dict, list)):
            return value

        # Пытаемся распарсить JSON строку
        if isinstance(value, str):
            try:
                return json.loads(value)
            except ValueError:
                # Если не JSON - возвращаем как строку
                return value

        # Для других типов - конвертируем в строку
        return str(value)

    def shutdown(self) -> None:
        """
        Завершает работу exporter.

        Вызывается при остановке приложения (синхронно).
        Стандартный метод OpenTelemetry SpanExporter.

        С SimpleSpanProcessor все spans экспортируются синхронно,
        но background tasks для _export_span могут еще выполняться.
        TracerProvider.shutdown() вызывает force_flush() перед shutdown().
        """
        if self._background_tasks:
            logger.debug(f"ℹ️ {len(self._background_tasks)} background tasks еще выполняются")
            # Не пытаемся их ждать - они завершатся сами
            # SimpleSpanProcessor уже вызвал force_flush() перед shutdown()

        logger.info("🛑 DatabaseSpanExporter завершен")

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """
        Принудительно отправляет все накопленные spans.

        С SimpleSpanProcessor spans экспортируются синхронно при span.end(),
        поэтому накопления нет. Background tasks (_export_span) могут еще
        выполняться, но они завершатся сами (fire-and-forget).

        Args:
            timeout_millis: Таймаут в миллисекундах

        Returns:
            True (spans уже экспортированы)
        """
        if self._background_tasks:
            logger.debug(
                f"ℹ️ force_flush: {len(self._background_tasks)} background tasks "
                f"еще сохраняют spans в БД (fire-and-forget)"
            )

        # SimpleSpanProcessor уже вызвал export() для всех spans
        # Background tasks для БД завершатся сами
        return True


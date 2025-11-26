"""
API для работы с OpenTelemetry трейсами.

Эндпоинты для получения списка трейсов и детальной информации.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List
from datetime import datetime
import json


from apps.agents.models.trace_models import TraceInfo, TraceDetail, SpanRecord, SpanStatus, SpanType

router = APIRouter(prefix="/traces", tags=["traces"])


@router.get("/", response_model=List[TraceInfo])
async def get_traces(
    limit: int = Query(100, ge=1, le=500, description="Количество трейсов"),
    offset: int = Query(0, ge=0, description="Смещение"),
    status: Optional[SpanStatus] = Query(None, description="Фильтр по статусу"),
    span_type: Optional[SpanType] = Query(None, description="Фильтр по типу root span"),
) -> List[TraceInfo]:
    """
    Получить список трейсов.

    Трейсы группируются по trace_id и сортируются по времени начала.
    """

    # Получаем все spans из БД
    all_span_keys = await storage.list_by_prefix("otel:", limit= 10000)

    # Парсим spans
    traces_map = {}

    for key in all_span_keys:
        span_data = await storage.get(key)
        if not span_data:
            continue

        span = SpanRecord.model_validate_json(span_data)

        # Применяем фильтры
        if status and span.status != status:
            continue

        # Группируем по trace_id
        if span.trace_id not in traces_map:
            traces_map[span.trace_id] = {
                "spans": [],
                "root_span": None,
                "start_time": span.start_time,
                "end_time": span.end_time,
                "total_cost": 0,
                "error_count": 0,
            }

        trace_data = traces_map[span.trace_id]
        trace_data["spans"].append(span)

        # Обновляем статистику
        if span.cost:
            trace_data["total_cost"] += span.cost
        if span.status == SpanStatus.ERROR:
            trace_data["error_count"] += 1

        # Находим root span (без parent_span_id)
        if not span.parent_span_id:
            trace_data["root_span"] = span

        # Обновляем time range
        if span.start_time < trace_data["start_time"]:
            trace_data["start_time"] = span.start_time
        if span.end_time and (not trace_data["end_time"] or span.end_time > trace_data["end_time"]):
            trace_data["end_time"] = span.end_time

    # Создаем TraceInfo объекты
    traces = []
    for trace_id, data in traces_map.items():
        root_span = data["root_span"]
        if not root_span:
            # Если нет root span, берем первый span
            root_span = data["spans"][0] if data["spans"] else None

        if not root_span:
            continue

        # Применяем фильтр по span_type
        if span_type and root_span.span_type != span_type:
            continue

        # Вычисляем длительность трейса
        duration_ms = None
        if data["end_time"] and data["start_time"]:
            duration_ms = (data["end_time"] - data["start_time"]).total_seconds() * 1000

        # Определяем статус трейса
        trace_status = SpanStatus.SUCCESS
        if data["error_count"] > 0:
            trace_status = SpanStatus.ERROR
        elif any(span.status == SpanStatus.PENDING for span in data["spans"]):
            trace_status = SpanStatus.PENDING

        trace_info = TraceInfo(
            trace_id=trace_id,
            name=root_span.name,
            status=trace_status,
            start_time=data["start_time"],
            end_time=data["end_time"],
            duration_ms=duration_ms,
            total_spans=len(data["spans"]),
            total_cost=data["total_cost"] if data["total_cost"] > 0 else None,
            error_count=data["error_count"],
            root_span_type=root_span.span_type,
        )
        traces.append(trace_info)

    # Сортируем по времени начала (новые первыми)
    traces.sort(key=lambda t: t.start_time, reverse=True)

    # Применяем пагинацию
    return traces[offset:offset + limit]


@router.get("/{trace_id}", response_model=TraceDetail)
async def get_trace_detail(
    trace_id: str,
) -> TraceDetail:
    """
    Получить детальную информацию о трейсе со всеми spans.

    Spans отсортированы по времени начала для построения таймлайна.
    """

    # Получаем spans конкретного трейса (формат: otel:{trace_id}:span:{span_id})
    span_keys = await storage.list_by_prefix(f"otel:{trace_id}:span:", limit = 10000)

    spans = []
    for key in span_keys:
        span_data = await storage.get(key)
        if not span_data:
            continue

        span = SpanRecord.model_validate_json(span_data)
        spans.append(span)

    if not spans:
        raise HTTPException(status_code=404, detail=f"Трейс {trace_id} не найден")

    # Сортируем по времени начала
    spans.sort(key=lambda s: s.start_time)

    # Находим root span
    root_span = next((s for s in spans if not s.parent_span_id), spans[0])

    # Вычисляем статистику
    total_cost = sum(s.cost for s in spans if s.cost)
    error_count = sum(1 for s in spans if s.status == SpanStatus.ERROR)

    # Определяем статус трейса
    trace_status = SpanStatus.SUCCESS
    if error_count > 0:
        trace_status = SpanStatus.ERROR
    elif any(s.status == SpanStatus.PENDING for s in spans):
        trace_status = SpanStatus.PENDING

    # Вычисляем time range
    start_time = min(s.start_time for s in spans)
    end_time = max((s.end_time for s in spans if s.end_time), default=None)

    duration_ms = None
    if end_time:
        duration_ms = (end_time - start_time).total_seconds() * 1000

    # Создаем TraceInfo
    trace_info = TraceInfo(
        trace_id=trace_id,
        name=root_span.name,
        status=trace_status,
        start_time=start_time,
        end_time=end_time,
        duration_ms=duration_ms,
        total_spans=len(spans),
        total_cost=total_cost if total_cost > 0 else None,
        error_count=error_count,
        root_span_type=root_span.span_type,
    )

    return TraceDetail(
        trace_info=trace_info,
        spans=spans,
    )




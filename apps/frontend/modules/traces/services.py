"""
Сервисные функции для работы с traces
"""

from typing import List, Dict, Optional

from core.models.trace_models import SpanRecord, TraceInfo, SpanStatus


async def load_spans_from_storage(storage, prefix: str = "otel:") -> List[SpanRecord]:
    """Загружает все spans из storage"""
    span_keys = await storage.list_by_prefix(prefix)
    spans = []

    for key in span_keys:
        # Читаем по полному ключу (формат: otel:{trace_id}:span:{span_id})
        span_data = await storage.get(key)
        if not span_data:
            continue

        try:
            span = SpanRecord.model_validate_json(span_data)
            spans.append(span)
        except Exception:
            continue

    return spans


def group_spans_by_trace(spans: List[SpanRecord]) -> Dict[str, Dict]:
    """Группирует spans по trace_id"""
    traces_map = {}

    for span in spans:
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

        if span.cost:
            trace_data["total_cost"] += span.cost
        if span.status == SpanStatus.ERROR:
            trace_data["error_count"] += 1

        if not span.parent_span_id:
            trace_data["root_span"] = span

        if span.start_time < trace_data["start_time"]:
            trace_data["start_time"] = span.start_time
        if span.end_time and (not trace_data["end_time"] or span.end_time > trace_data["end_time"]):
            trace_data["end_time"] = span.end_time

    return traces_map


def calculate_trace_stats(trace_data: Dict) -> Dict:
    """Вычисляет статистику трейса"""
    duration_ms = None
    if trace_data["end_time"] and trace_data["start_time"]:
        duration_ms = (trace_data["end_time"] - trace_data["start_time"]).total_seconds() * 1000

    trace_status = SpanStatus.SUCCESS
    if trace_data["error_count"] > 0:
        trace_status = SpanStatus.ERROR
    elif any(span.status == SpanStatus.PENDING for span in trace_data["spans"]):
        trace_status = SpanStatus.PENDING

    return {
        "duration_ms": duration_ms,
        "status": trace_status,
    }


def find_root_span(trace_data: Dict) -> Optional[SpanRecord]:
    """Находит root span в трейсе"""
    if trace_data["root_span"]:
        return trace_data["root_span"]
    return trace_data["spans"][0] if trace_data["spans"] else None


def merge_trace_metadata(spans: List[SpanRecord], root_span: SpanRecord) -> Dict:
    """Объединяет метаданные из всех spans (приоритет у root span)"""
    metadata = {}

    if root_span.metadata:
        metadata.update(root_span.metadata)

    for span in spans:
        if span.span_id != root_span.span_id and span.metadata:
            for key, value in span.metadata.items():
                if key not in metadata:
                    metadata[key] = value

    return metadata


def build_trace_info(trace_id: str, trace_data: Dict) -> TraceInfo:
    """Создает TraceInfo объект из данных трейса"""
    root_span = find_root_span(trace_data)
    if not root_span:
        raise ValueError(f"Root span не найден для трейса {trace_id}")

    stats = calculate_trace_stats(trace_data)
    metadata = merge_trace_metadata(trace_data["spans"], root_span)

    return TraceInfo(
        trace_id=trace_id,
        name=root_span.name,
        status=stats["status"],
        start_time=trace_data["start_time"],
        end_time=trace_data["end_time"],
        duration_ms=stats["duration_ms"],
        total_spans=len(trace_data["spans"]),
        total_cost=trace_data["total_cost"] if trace_data["total_cost"] > 0 else None,
        error_count=trace_data["error_count"],
        root_span_type=root_span.span_type,
        metadata=metadata,
    )


def filter_spans(
    spans: List[SpanRecord],
    status: Optional[str] = None,
    span_type: Optional[str] = None,
) -> List[SpanRecord]:
    """Фильтрует spans по статусу"""
    filtered = spans

    if status:
        filtered = [s for s in filtered if s.status.value == status]

    if span_type:
        filtered = [s for s in filtered if s.span_type.value == span_type]

    return filtered


def filter_traces(
    traces_map: Dict[str, Dict],
    span_type: Optional[str] = None,
) -> Dict[str, Dict]:
    """Фильтрует трейсы по типу root span"""
    if not span_type:
        return traces_map

    filtered = {}
    for trace_id, trace_data in traces_map.items():
        root_span = find_root_span(trace_data)
        if root_span and root_span.span_type.value == span_type:
            filtered[trace_id] = trace_data

    return filtered


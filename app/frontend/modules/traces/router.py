"""
Роутер для страницы трейсов OpenTelemetry
"""

from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse
from typing import Optional

from app.frontend.core.template_loader import get_templates
from app.frontend.core.utils import render_with_dashboard
from app.frontend.dependencies import StorageDep
from app.models.trace_models import TraceInfo, SpanStatus

from .services import (
    load_spans_from_storage,
    group_spans_by_trace,
    build_trace_info,
    filter_spans,
    filter_traces,
)

router = APIRouter(prefix="/frontend/traces", tags=["traces"])
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def traces_page(request: Request):
    """Главная страница трейсов"""
    return await render_with_dashboard(
        request=request,
        content_template="traces.html",
        context={"request": request},
        content_url="/frontend/traces/",
    )


@router.get("/list", response_class=HTMLResponse)
async def get_traces_table(
    request: Request,
    storage: StorageDep,
    status: Optional[str] = Query(None),
    span_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Получает таблицу трейсов с фильтрацией (HTMX endpoint)"""

    spans = await load_spans_from_storage(storage)
    spans = filter_spans(spans, status=status)

    traces_map = group_spans_by_trace(spans)
    traces_map = filter_traces(traces_map, span_type=span_type)

    traces = []
    for trace_id, trace_data in traces_map.items():
        try:
            trace_info = build_trace_info(trace_id, trace_data)
            traces.append(trace_info)
        except ValueError:
            continue

    traces.sort(key=lambda t: t.start_time, reverse=True)
    paginated_traces = traces[offset:offset + limit]

    return templates.TemplateResponse(
        "traces_table.html",
        {
            "request": request,
            "traces": paginated_traces,
            "total": len(traces),
            "limit": limit,
            "offset": offset,
        }
    )


@router.get("/{trace_id}", response_class=HTMLResponse)
async def get_trace_detail_modal(
    request: Request,
    trace_id: str,
    storage: StorageDep,
):
    """Получает модальное окно с детальной информацией о трейсе (HTMX endpoint)"""

    spans = await load_spans_from_storage(storage)
    spans = [s for s in spans if s.trace_id == trace_id]

    if not spans:
        raise HTTPException(status_code=404, detail=f"Трейс {trace_id} не найден")

    spans.sort(key=lambda s: s.start_time)
    traces_map = group_spans_by_trace(spans)
    trace_data = traces_map.get(trace_id)

    if not trace_data:
        raise HTTPException(status_code=404, detail=f"Трейс {trace_id} не найден")

    trace_info = build_trace_info(trace_id, trace_data)

    return templates.TemplateResponse(
        "trace_detail.html",
        {
            "request": request,
            "trace_info": trace_info.model_dump(mode='json'),
            "spans": [span.model_dump(mode='json') for span in spans],
        }
    )


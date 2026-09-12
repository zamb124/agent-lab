"""Спецификация Flow UI для редактора: JSON Schema грамматики, галерея шаблонов, AI-помощник."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.responses import JSONResponse

from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models.flow_ui_assist import (
    FlowUIAssistOutputError,
    FlowUIAssistRequest,
    FlowUIAssistResult,
)
from core.context import require_context
from core.flow_ui.document import FlowUIDocument
from core.flow_ui.templates import FlowUITemplate, flow_ui_templates
from core.pagination import OffsetPage
from core.state.mutation_policy import FROZEN_STATE_FIELDS
from core.types import JsonObject, require_json_object

router = APIRouter(prefix="/flow-ui", tags=["flows", "flow-ui"])


def flow_ui_schema() -> JsonObject:
    """JSON Schema документа интерфейса; Pydantic-грамматика — единственный источник.

    ``x-flow-ui-frozen-state-fields`` — системные поля state, на которые редактор
    запрещает ссылаться в ``field`` и шаблонах (источник — ``mutation_policy``).
    """
    schema = require_json_object(FlowUIDocument.model_json_schema(), "FlowUIDocument schema")
    schema["x-flow-ui-frozen-state-fields"] = sorted(FROZEN_STATE_FIELDS)
    return schema


@router.get("/schema")
async def get_flow_ui_schema(container: ContainerDep) -> JsonObject:
    _ = container
    _ = require_context()
    return flow_ui_schema()


@router.get("/templates", response_model=OffsetPage[FlowUITemplate])
async def list_flow_ui_templates(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[FlowUITemplate]:
    """Галерея готовых документов на языке запроса."""
    _ = container
    templates = flow_ui_templates(require_context().language)
    return OffsetPage[FlowUITemplate](
        items=templates[offset : offset + limit],
        total=len(templates),
        limit=limit,
        offset=offset,
    )


async def _assist_output_error_handler(request: Request, exc: Exception) -> JSONResponse:
    _ = request
    return JSONResponse(
        status_code=502,
        content={"detail": str(exc), "code": "flow_ui_assist_invalid_output"},
    )


def install_flow_ui_exception_handlers(app: FastAPI) -> None:
    """Противоречивый ответ LLM-помощника — ошибка upstream (502), не 500 платформы."""
    app.add_exception_handler(FlowUIAssistOutputError, _assist_output_error_handler)


@router.post("/assist", response_model=FlowUIAssistResult)
async def assist_flow_ui(
    container: ContainerDep, request: FlowUIAssistRequest
) -> FlowUIAssistResult:
    """«Описать страницу» (``block_id`` пуст) или «Изменить выбранный блок» — structured output по грамматике."""
    _ = require_context()
    return await container.flow_ui_assist_service.assist(request)

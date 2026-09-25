"""REST-зеркало каталога сессий: query/path → тот же `op_*`, что и WS."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Path, Query

from apps.flows.di import Di
from apps.flows.realtime.session_operations import (
    op_flows_sessions_list,
    op_flows_sessions_remove,
)
from apps.flows.src.models.session_config import (
    SessionConfig,
    SessionDeletedResponse,
    SessionIdPayload,
    SessionListPayload,
)
from core.context import require_context
from core.pagination import OffsetPage

router = APIRouter(tags=["sessions"])


@router.get("/", response_model=OffsetPage[SessionConfig])
async def list_sessions(
    di: Di,
    user_id: Annotated[str | None, Query(description="Фильтр по пользователю")] = None,
    flow_id: Annotated[str | None, Query(description="Фильтр по flow")] = None,
    branch_id: Annotated[str | None, Query(description="Фильтр по ветке (branch_id)")] = None,
    date_from: Annotated[datetime | None, Query(description="Начало периода")] = None,
    date_to: Annotated[datetime | None, Query(description="Конец периода")] = None,
    limit: Annotated[int, Query(ge=1, le=200, description="Максимум записей")] = 50,
    offset: Annotated[int, Query(ge=0, description="Смещение")] = 0,
) -> OffsetPage[SessionConfig]:
    return await op_flows_sessions_list(
        SessionListPayload(
            user_id=user_id,
            flow_id=flow_id,
            branch_id=branch_id,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        ),
        user=require_context().user,
        di=di,
    )


@router.delete("/{session_id}", response_model=SessionDeletedResponse)
async def delete_session(
    di: Di,
    session_id: Annotated[str, Path(description="ID сессии для удаления")],
) -> SessionDeletedResponse:
    return await op_flows_sessions_remove(
        SessionIdPayload(session_id=session_id),
        user=require_context().user,
        di=di,
    )

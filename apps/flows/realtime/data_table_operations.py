"""DataTable create в scope flow: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from apps.flows.di import Di
from apps.flows.realtime.operations import (
    require_company_member,
    require_edit_flow,
)
from core.data_tables.models import DataTableCreateRequest, DataTableScope
from core.data_tables.service import DataTableNotFoundError
from core.files.models import FileRecord
from core.models.identity_models import User
from core.websocket import (
    raise_invalid,
)

_FLOW_SCOPES: frozenset[DataTableScope] = frozenset({"flow_asset", "flow_session"})


async def op_flows_data_tables_create(
    payload: DataTableCreateRequest,
    *,
    user: User,
    di: Di,
) -> FileRecord:
    _ = user
    if payload.scope not in _FLOW_SCOPES:
        raise_invalid(ValueError("scope must be flow_asset or flow_session"))
    if payload.flow_id is None or payload.flow_id.strip() == "":
        _ = await require_company_member(di)
    else:
        _ = await require_edit_flow(di, payload.flow_id)
    try:
        return await di.data_table_service.create(
            original_name=payload.original_name,
            scope=payload.scope,
            flow_id=payload.flow_id,
            session_id=payload.session_id,
            tables=payload.tables,
        )
    except (DataTableNotFoundError, ValueError) as exc:
        raise_invalid(exc)

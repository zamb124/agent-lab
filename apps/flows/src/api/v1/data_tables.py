"""REST-зеркало DataTable create: body → тот же `op_*`, что и WS."""

from fastapi import APIRouter

from apps.flows.di import Di
from apps.flows.realtime.data_table_operations import op_flows_data_tables_create
from core.context import require_context
from core.data_tables.models import DataTableCreateRequest
from core.files.models import FileRecord

router = APIRouter(tags=["data-tables"])


@router.post("/data-tables", response_model=FileRecord)
async def create_flow_data_table(
    body: DataTableCreateRequest,
    di: Di,
) -> FileRecord:
    return await op_flows_data_tables_create(
        body,
        user=require_context().user,
        di=di,
    )

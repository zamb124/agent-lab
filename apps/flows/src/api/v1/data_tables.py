"""Flows HTTP: create DataTable files in flow_asset / flow_session scope."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from apps.flows.src.dependencies import ContainerDep
from core.data_tables.models import DataTableCreateRequest
from core.data_tables.service import DataTableNotFoundError
from core.files.models import FileRecord

router = APIRouter(tags=["data-tables"])


@router.post("/data-tables", response_model=FileRecord)
async def create_flow_data_table(
    body: DataTableCreateRequest,
    container: ContainerDep,
) -> FileRecord:
    if body.scope not in {"flow_asset", "flow_session"}:
        raise HTTPException(
            status_code=400,
            detail="scope must be flow_asset or flow_session",
        )
    try:
        return await container.data_table_service.create(
            original_name=body.original_name,
            scope=body.scope,
            flow_id=body.flow_id,
            session_id=body.session_id,
            tables=body.tables,
        )
    except (DataTableNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

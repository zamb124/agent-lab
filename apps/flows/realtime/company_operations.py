"""Постановка init ресурсов компании в очередь: один `op_*` для REST и WS RPC."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from apps.flows.di import Di
from apps.flows.realtime.operations import (
    company_scope,
)
from apps.flows.src.tasks.task_names import TASK_INIT_COMPANY_RESOURCES
from core.models.base import StrictBaseModel
from core.models.identity_models import User
from core.tasks import enqueue
from core.websocket import (
    raise_forbidden,
)


class CompanyInitPayload(StrictBaseModel):
    company_id: str = Field(min_length=1)
    company_name: str = ""
    subdomain: str = ""


class CompanyInitScheduledResponse(StrictBaseModel):
    task_id: str
    status: Literal["scheduled"]


async def op_flows_company_init(
    payload: CompanyInitPayload,
    *,
    user: User,
    di: Di,
) -> CompanyInitScheduledResponse:
    _ = user
    _ = di
    scope = company_scope()
    if payload.company_id != scope.company_id:
        raise_forbidden(
            ValueError(
                f"company_id {payload.company_id!r} does not match active company {scope.company_id!r}"
            )
        )
    task = await enqueue(
        TASK_INIT_COMPANY_RESOURCES,
        company_id=payload.company_id,
        company_name=payload.company_name,
        subdomain=payload.subdomain,
        background_kind="company_init",
    )
    task_id = task.task_id
    if not task_id:
        raise RuntimeError("enqueue company init: empty task_id")
    return CompanyInitScheduledResponse(task_id=task_id, status="scheduled")

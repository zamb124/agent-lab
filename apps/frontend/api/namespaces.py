"""API управления platform namespaces в console frontend."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from apps.frontend.dependencies import ContainerDep, require_frontend_user
from core.models.identity_models import NamespaceKind
from core.namespace import TECHNICAL_NAMESPACE_NAME_PREFIXES, personal_namespace_name
from core.pagination import OffsetPage

router = APIRouter(prefix="/api/namespaces", tags=["namespaces"])


class ConsoleNamespaceItem(BaseModel):
    """Запись namespace для admin console."""

    name: str
    company_id: str
    description: str | None = None
    is_default: bool = False
    kind: NamespaceKind
    owner_user_id: str | None = None


class ConsoleNamespaceCreateRequest(BaseModel):
    """Lightweight create company_workspace без CRM template."""

    name: str = Field(min_length=1, max_length=100)
    description: str | None = None


async def _require_company_admin(container: ContainerDep) -> None:
    user = require_frontend_user()
    company_id = user.active_company_id.strip()
    if company_id == "":
        raise HTTPException(status_code=400, detail="active_company_id is required")
    await container.authz_service.require_company_admin(
        company_id=company_id,
        user_id=user.user_id,
    )


@router.get("", response_model=OffsetPage[ConsoleNamespaceItem])
async def list_console_namespaces(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
    kind: Annotated[
        Literal["company_workspace", "personal", "all"] | None,
        Query(),
    ] = "all",
) -> OffsetPage[ConsoleNamespaceItem]:
    """Список namespaces: company_workspace + personal (technical скрыты). Admin only."""
    await _require_company_admin(container)
    if kind == "company_workspace":
        kinds = frozenset({NamespaceKind.COMPANY_WORKSPACE})
    elif kind == "personal":
        kinds = frozenset({NamespaceKind.PERSONAL})
    else:
        kinds = frozenset({NamespaceKind.COMPANY_WORKSPACE, NamespaceKind.PERSONAL})

    namespaces, total = (
        await container.namespace_service.list(limit=limit, offset=offset, kinds=kinds),
        await container.namespace_service.count(kinds=kinds),
    )
    return OffsetPage[ConsoleNamespaceItem](
        items=[
            ConsoleNamespaceItem(
                name=ns.name,
                company_id=ns.company_id,
                description=ns.description,
                is_default=ns.is_default,
                kind=ns.kind,
                owner_user_id=ns.owner_user_id,
            )
            for ns in namespaces
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=ConsoleNamespaceItem, status_code=201)
async def create_console_namespace(
    body: ConsoleNamespaceCreateRequest,
    container: ContainerDep,
) -> ConsoleNamespaceItem:
    """Lightweight company_workspace без CRM template. Admin only."""
    await _require_company_admin(container)
    name = body.name.strip()
    if name == "":
        raise HTTPException(status_code=422, detail="name is required")
    if name.startswith("user-") or any(
        name.startswith(prefix) for prefix in TECHNICAL_NAMESPACE_NAME_PREFIXES
    ):
        raise HTTPException(status_code=422, detail="reserved namespace name prefix")
    try:
        ns = await container.namespace_service.create(
            name=name,
            description=body.description,
            kind=NamespaceKind.COMPANY_WORKSPACE,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ConsoleNamespaceItem(
        name=ns.name,
        company_id=ns.company_id,
        description=ns.description,
        is_default=ns.is_default,
        kind=ns.kind,
        owner_user_id=ns.owner_user_id,
    )


@router.get("/me/personal", response_model=ConsoleNamespaceItem)
async def get_my_personal_namespace(container: ContainerDep) -> ConsoleNamespaceItem:
    """Personal namespace текущего пользователя (ensure)."""
    user = require_frontend_user()
    ns = await container.namespace_service.ensure_personal_namespace(
        user.user_id,
        display_name=user.name,
    )
    expected = personal_namespace_name(user.user_id)
    if ns.name != expected:
        raise HTTPException(status_code=500, detail="personal namespace name mismatch")
    return ConsoleNamespaceItem(
        name=ns.name,
        company_id=ns.company_id,
        description=ns.description,
        is_default=ns.is_default,
        kind=ns.kind,
        owner_user_id=ns.owner_user_id,
    )

"""Список рабочих пространств для переключателя в сайдбаре wiki."""

from fastapi import APIRouter, HTTPException

from apps.wiki.dependencies import ContainerDep
from core.context import get_context
from core.models.base import StrictBaseModel
from core.pagination import OffsetPage

router = APIRouter(prefix="/namespaces", tags=["wiki-namespaces"])


class WikiNamespaceItem(StrictBaseModel):
    """Пространство компании в списке переключателя."""

    name: str
    is_default: bool = False


@router.get("", response_model=OffsetPage[WikiNamespaceItem])
async def list_wiki_namespaces(container: ContainerDep) -> OffsetPage[WikiNamespaceItem]:
    """Company workspaces активной компании.

    Personal и technical пространства в продуктовый список не попадают —
    это тот же контракт, что у Documents и Networkle.
    """
    context = get_context()
    if context is None or context.active_company is None:
        raise HTTPException(status_code=403, detail="Компания не выбрана")

    rows = await container.namespace_service.list_company_workspaces(limit=1000)
    items = [
        WikiNamespaceItem(name=namespace.name.strip(), is_default=bool(namespace.is_default))
        for namespace in rows
        if namespace.name.strip()
    ]
    return OffsetPage[WikiNamespaceItem](
        items=items, total=len(items), limit=len(items), offset=0
    )

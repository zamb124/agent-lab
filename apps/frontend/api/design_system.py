"""Public UI Kit catalog API and component playground preview."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, JSONResponse

from apps.frontend.di import Di
from apps.frontend.services.design_system_catalog import (
    catalog_allows_component,
    load_catalog,
    load_manifest,
    resolve_variant,
)
from apps.frontend.services.design_system_preview_html import build_design_system_preview_html
from core.websocket import WsCommandError, raise_not_found

router = APIRouter(tags=["design-system"])


@router.get("/api/design-system/catalog")
async def get_design_system_catalog(di: Di) -> JSONResponse:
    _ = di
    entries = load_catalog()
    payload = {
        "components": [
            {
                "component": entry.component,
                "doc_slug": entry.doc_slug,
                "status": entry.status,
                "tier": entry.tier,
                "deadline": entry.deadline,
            }
            for entry in entries
        ]
    }
    return JSONResponse(content=payload)


@router.get("/design-system/preview", response_class=HTMLResponse)
@router.get("/frontend/design-system/preview", response_class=HTMLResponse)
async def design_system_preview(
    di: Di,
    component: Annotated[str, Query(min_length=1)],
    variant: Annotated[str, Query(min_length=1)] = "default",
) -> HTMLResponse:
    _ = di
    trimmed = component.strip()
    variant_id = variant.strip()
    if not catalog_allows_component(trimmed):
        raise WsCommandError("not_found", "Component not in UI Kit catalog", error_code="not_found")
    manifest = load_manifest(trimmed)
    try:
        resolved = resolve_variant(trimmed, variant_id)
    except ValueError as exc:
        raise_not_found(exc)
    html_out = build_design_system_preview_html(
        component=trimmed,
        variant_id=resolved.id,
        import_path=manifest.import_path,
        props=resolved.props,
        title=manifest.title_ru,
    )
    return HTMLResponse(content=html_out)

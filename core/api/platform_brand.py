"""Публичный API бренда платформы по Host header."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.config.models import LegalConfig, PublicSiteConfig
from core.platform_brand.resolver import (
    UnknownPlatformDomainError,
    resolve_brand,
    resolve_brand_apex_origin,
    supported_domains,
)
from core.utils.domain import extract_base_domain

router = APIRouter(prefix="/api/platform", tags=["platform-brand"])


class PlatformBrandResponse(BaseModel):
    base_domain: str
    platform_name: str
    support_email: str
    agent_product_name: str
    models_product_name: str
    voice_product_name: str
    llms_display_label: str
    flows_product_label: str
    logo_path: str
    apex_origin: str
    legal: LegalConfig
    public_site: PublicSiteConfig
    supported_domains: list[str] = Field(
        description="Все registrable apex platform brands (для JS host guard).",
    )


@router.options("/brand")
async def options_platform_brand(request: Request) -> JSONResponse:
    response = JSONResponse(content={})
    _apply_platform_brand_cors(request, response)
    return response


@router.get("/brand", response_model=PlatformBrandResponse)
async def get_platform_brand(request: Request) -> JSONResponse:
    host = request.headers.get("host")
    if host is None or not str(host).strip():
        raise HTTPException(status_code=400, detail="Host header is required")
    try:
        brand = resolve_brand(host)
        base_domain = extract_base_domain(host)
    except (UnknownPlatformDomainError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = PlatformBrandResponse(
        base_domain=base_domain,
        platform_name=brand.platform_name,
        support_email=brand.support_email,
        agent_product_name=brand.agent_product_name,
        models_product_name=brand.models_product_name,
        voice_product_name=brand.voice_product_name,
        llms_display_label=brand.llms_display_label,
        flows_product_label=brand.flows_product_label,
        logo_path=brand.logo_path,
        apex_origin=resolve_brand_apex_origin(host, url_scheme=request.url.scheme),
        legal=brand.legal,
        public_site=brand.public_site,
        supported_domains=list(supported_domains()),
    )
    response = JSONResponse(content=payload.model_dump(mode="json"))
    _apply_platform_brand_cors(request, response)
    return response


def _apply_platform_brand_cors(request: Request, response: JSONResponse) -> None:
    origin = request.headers.get("origin")
    if origin is not None and str(origin).strip():
        response.headers["Access-Control-Allow-Origin"] = str(origin).strip()
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Accept"

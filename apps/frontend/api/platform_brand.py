"""Публичный API бренда платформы по Host header."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.config.models import LegalConfig, PublicSiteConfig
from core.platform_brand.resolver import (
    UnknownPlatformDomainError,
    resolve_brand,
    resolve_public_base_url,
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


@router.get("/brand", response_model=PlatformBrandResponse)
async def get_platform_brand(request: Request) -> PlatformBrandResponse:
    host = request.headers.get("host")
    if host is None or not str(host).strip():
        raise HTTPException(status_code=400, detail="Host header is required")
    try:
        brand = resolve_brand(host)
        base_domain = extract_base_domain(host)
    except (UnknownPlatformDomainError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PlatformBrandResponse(
        base_domain=base_domain,
        platform_name=brand.platform_name,
        support_email=brand.support_email,
        agent_product_name=brand.agent_product_name,
        models_product_name=brand.models_product_name,
        voice_product_name=brand.voice_product_name,
        llms_display_label=brand.llms_display_label,
        flows_product_label=brand.flows_product_label,
        logo_path=brand.logo_path,
        apex_origin=resolve_public_base_url(host).rstrip("/") + "/",
        legal=brand.legal,
        public_site=brand.public_site,
        supported_domains=list(supported_domains()),
    )

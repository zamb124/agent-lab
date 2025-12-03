"""
Router для RAG UI - standalone интерфейс
"""

import logging
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from apps.frontend.core.template_loader import get_templates
from core.config import get_settings
from core.rag.factory import RAG_PROVIDERS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["rag-pages"])
templates = get_templates()


def get_enabled_providers() -> list:
    """Получить список включенных провайдеров"""
    settings = get_settings()
    
    if not settings.rag.enabled:
        return []
    
    providers = []
    default_provider = settings.rag.default_provider
    
    for name in RAG_PROVIDERS.keys():
        provider_config = settings.rag.providers.get(name)
        if provider_config:
            enabled = provider_config.enabled if hasattr(provider_config, 'enabled') else False
            if enabled:
                providers.append({
                    "name": name,
                    "is_default": name == default_provider
                })
    
    return providers


@router.get("/", response_class=HTMLResponse)
async def rag_dashboard(request: Request):
    """Главная страница RAG Dashboard"""
    providers = get_enabled_providers()
    default_provider = next((p["name"] for p in providers if p["is_default"]), None)
    
    if not default_provider and providers:
        default_provider = providers[0]["name"]
    
    return templates.TemplateResponse(
        "rag_base.html",
        {
            "request": request,
            "providers": providers,
            "current_provider": default_provider,
            "current_namespace": None
        }
    )


@router.get("/namespace/{namespace_id}", response_class=HTMLResponse)
async def rag_namespace_view(request: Request, namespace_id: str):
    """Страница просмотра неймспейса"""
    providers = get_enabled_providers()
    default_provider = next((p["name"] for p in providers if p["is_default"]), None)
    
    if not default_provider and providers:
        default_provider = providers[0]["name"]
    
    return templates.TemplateResponse(
        "rag_base.html",
        {
            "request": request,
            "providers": providers,
            "current_provider": default_provider,
            "current_namespace": namespace_id
        }
    )


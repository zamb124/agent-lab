"""API роутеры Sync Service."""

from fastapi import APIRouter

from apps.sync.api.calls import router as calls_router
from apps.sync.api.channels import router as channels_router
from apps.sync.api.company import router as company_router
from apps.sync.api.files_meta import router as files_meta_router
from apps.sync.api.git import router as git_router
from apps.sync.api.messages import router as messages_router
from apps.sync.api.platform_namespaces import router as platform_namespaces_router
from apps.sync.api.spaces import router as spaces_router
from apps.sync.api.threads import router as threads_router


def get_api_router() -> APIRouter:
    """Собирает API роутеры Sync (файловый роутер добавляется через create_service_app)."""
    api = APIRouter()
    api.include_router(spaces_router, prefix="/spaces", tags=["spaces"])
    api.include_router(platform_namespaces_router, prefix="/platform-namespaces", tags=["platform-namespaces"])
    api.include_router(company_router, prefix="/company", tags=["company"])
    api.include_router(channels_router, prefix="/channels", tags=["channels"])
    api.include_router(threads_router, prefix="/threads", tags=["threads"])
    api.include_router(messages_router, prefix="/channels", tags=["messages"])
    api.include_router(git_router, prefix="/git", tags=["git"])
    api.include_router(calls_router, prefix="/calls", tags=["calls"])
    api.include_router(files_meta_router, prefix="/files", tags=["files"])
    return api

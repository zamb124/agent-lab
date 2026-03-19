"""API роутеры Sync Service."""

from fastapi import APIRouter

from apps.sync.api.spaces import router as spaces_router
from apps.sync.api.channels import router as channels_router
from apps.sync.api.threads import router as threads_router
from apps.sync.api.messages import router as messages_router
from apps.sync.api.files import router as files_router
from apps.sync.api.git import router as git_router


def get_api_router() -> APIRouter:
    """Собирает все API роутеры Sync."""
    api = APIRouter()
    api.include_router(spaces_router, prefix="/spaces", tags=["spaces"])
    api.include_router(channels_router, prefix="/channels", tags=["channels"])
    api.include_router(threads_router, prefix="/threads", tags=["threads"])
    api.include_router(messages_router, prefix="/channels", tags=["messages"])
    api.include_router(files_router, prefix="/files", tags=["files"])
    api.include_router(git_router, prefix="/git", tags=["git"])
    return api


all_routers = [
    spaces_router,
    channels_router,
    threads_router,
    messages_router,
    files_router,
    git_router,
]

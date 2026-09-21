"""FastAPI entrypoint guest_runtime — ферма code_agent."""

from __future__ import annotations

import asyncio

from fastapi import FastAPI

from apps.guest_runtime.api.v1 import router as v1_router
from apps.guest_runtime.config import GuestRuntimeSettings, get_guest_runtime_settings
from apps.guest_runtime.container import (
    GuestRuntimeContainer,
    get_guest_runtime_container,
)
from apps.guest_runtime.services.slots import ensure_docker_network
from core.app import create_service_app
from core.billing import set_billing_service
from core.config import get_settings
from core.logging import get_logger
from core.utils.background import run_with_log_context

logger = get_logger(__name__)

_reaper_task: asyncio.Task[None] | None = None


async def on_startup(
    app: FastAPI, container: GuestRuntimeContainer, settings: GuestRuntimeSettings
) -> None:
    _ = app, settings
    farm = get_settings().guest_runtime
    if farm.max_concurrent_builds != 1:
        raise RuntimeError(
            f"guest_runtime.max_concurrent_builds must be 1, got {farm.max_concurrent_builds}"
        )
    await container.redis_client.connect()
    if not await container.redis_client.ping():
        raise RuntimeError("guest_runtime requires Redis")
    set_billing_service(container.billing_service)
    if farm.executor == "docker":
        await ensure_docker_network()
    interval = farm.reaper_interval_seconds

    async def _reaper_loop() -> None:
        while True:
            await asyncio.sleep(interval)
            await container.farm_service.reap()

    global _reaper_task
    _reaper_task = run_with_log_context(
        _reaper_loop(),
        name="guest_runtime.reaper",
        background_kind="polling",
    )
    logger.info("guest_runtime started")


async def on_shutdown(app: FastAPI, container: GuestRuntimeContainer) -> None:
    _ = app, container
    task = _reaper_task
    if task is None:
        raise RuntimeError("guest reaper task was not started")
    _ = task.cancel()


app = create_service_app(
    service_name="guest_runtime",
    settings_class=GuestRuntimeSettings,
    get_container=get_guest_runtime_container,
    routers=[v1_router],
    cors_origins=["*"],
    title="Platform Guest Runtime",
    description="Farm for code_agent nodes",
    version="1.0.0",
    api_version="v1",
    include_auth_middleware=False,
    include_crud_routers=False,
    include_tracing_lifecycle=True,
    include_platform_lifecycle=False,
    include_platform_routers=False,
    mount_repo_documentation=False,
    include_platform_pwa=False,
    documentation_gateway_prefix="guest-runtime",
    on_startup=on_startup,
    on_shutdown=on_shutdown,
)


if __name__ == "__main__":
    from core.app.server import serve

    serve(
        "guest_runtime",
        "apps.guest_runtime.main:app",
        get_guest_runtime_settings(),
    )

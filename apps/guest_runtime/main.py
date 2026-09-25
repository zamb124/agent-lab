"""FastAPI entrypoint guest_runtime — ферма code_agent."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from apps.guest_runtime.api.v1 import router as v1_router
from apps.guest_runtime.config import GuestRuntimeSettings, get_guest_runtime_settings
from apps.guest_runtime.di import GuestRuntimeDi
from apps.guest_runtime.services.farm_service import GuestFarmService
from apps.guest_runtime.services.slots import ensure_docker_network
from core.app import create_service_app
from core.clients.redis_client import RedisClient
from core.di import recipe
from core.logging import get_logger
from core.utils.background import run_with_log_context

logger = get_logger(__name__)


async def guest_reaper(
    farm_service: GuestFarmService,
    redis_client: RedisClient,
    settings: GuestRuntimeSettings,
) -> AsyncIterator[None]:
    farm = settings.guest_runtime
    if farm.max_concurrent_builds != 1:
        raise RuntimeError(
            f"guest_runtime.max_concurrent_builds must be 1, got {farm.max_concurrent_builds}"
        )
    await redis_client.connect()
    if not await redis_client.ping():
        raise RuntimeError("guest_runtime requires Redis")
    if farm.executor == "docker":
        await ensure_docker_network()
    interval = farm.reaper_interval_seconds

    async def _reaper_loop() -> None:
        while True:
            await asyncio.sleep(interval)
            await farm_service.reap()

    task = run_with_log_context(
        _reaper_loop(),
        name="guest_runtime.reaper",
        background_kind="polling",
    )
    logger.info("guest_runtime.guest_runtime")
    try:
        yield
    finally:
        _ = task.cancel()


app = create_service_app(
    "guest_runtime",
    GuestRuntimeSettings,
    GuestRuntimeDi,
    database="shared_url",
    lifecycle=(recipe(guest_reaper),),
    routers=[v1_router],
    cors_origins=["*"],
    title="Platform Guest Runtime",
    description="Farm for code_agent nodes",
    version="1.0.0",
    api_version="v1",
    include_auth_middleware=False,
    include_tracing_lifecycle=True,
    include_platform_lifecycle=False,
    include_platform_routers=False,
    mount_repo_documentation=False,
    include_platform_pwa=False,
    documentation_gateway_prefix="guest-runtime",
)


if __name__ == "__main__":
    from core.app.server import serve

    serve(
        "guest_runtime",
        "apps.guest_runtime.main:app",
        get_guest_runtime_settings(),
    )

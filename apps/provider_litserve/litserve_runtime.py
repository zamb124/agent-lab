"""Состояние LitServe-контура процесса. Создаётся при сборке приложения: маршруты /v1 сливаются до lifespan."""

from __future__ import annotations

import asyncio

import litserve as ls


class ProviderLitserveRuntime:
    def __init__(self) -> None:
        self.server: ls.LitServer | None = None
        self.manager: ls.LitServerManager | None = None
        self.response_task: asyncio.Task[None] | None = None

    def inference_started(self) -> bool:
        task = self.response_task
        return self.manager is not None and task is not None and not task.done()


provider_litserve_runtime = ProviderLitserveRuntime()

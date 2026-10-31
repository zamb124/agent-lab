"""Состояние LitServe-контура процесса.

``app`` привязывается в ``build_app`` — lifecycle-рецепт сливает маршруты ``/v1``
LitServer'а в основное приложение внутри lifespan (каталог моделей к тому
моменту уже прочитан из Postgres).
"""

from __future__ import annotations

import asyncio

import litserve as ls
from fastapi import FastAPI


class ProviderLitserveRuntime:
    def __init__(self) -> None:
        self.app: FastAPI | None = None
        self.server: ls.LitServer | None = None
        self.manager: ls.LitServerManager | None = None
        self.response_task: asyncio.Task[None] | None = None

    def attach_app(self, app: FastAPI) -> None:
        self.app = app

    def require_app(self) -> FastAPI:
        if self.app is None:
            raise RuntimeError("provider_litserve: FastAPI app is not attached to runtime")
        return self.app

    def inference_started(self) -> bool:
        task = self.response_task
        return self.manager is not None and task is not None and not task.done()


provider_litserve_runtime = ProviderLitserveRuntime()

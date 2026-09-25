"""Сервисы и воркеры платформы внутри процесса тестов.

Приложение сервиса обслуживает запросы только внутри своего lifespan: lifespan собирает
``<Svc>Di`` и публикует его в ``app.state``, как под Granian. ``ServiceProcesses.app``
поднимает lifespan приложения при первом обращении и держит его до конца сессии; уже
запущенный lifespan (фикстура теста вошла в него сама) используется как есть.

``sync_tools`` исполняет задачи TaskIQ в процессе теста и передаёт задаче DI её процесса,
как это делает ``task_di`` воркера: класс читается из аннотации параметра ``di`` задачи.
``FlowsDi`` и ``SyncDi`` — DI приложений flows и sync; DI воркера собирается при первой
его задаче поверх пулов Oxyde сессии и закрывается в конце сессии.
"""

from __future__ import annotations

import asyncio
import importlib
import typing
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import AsyncExitStack
from dataclasses import dataclass

import pytest_asyncio
from fastapi import FastAPI
from taskiq import AsyncTaskiqDecoratedTask

from apps.crm.config import CRMSettings
from apps.crm_worker.di import CrmWorkerDi
from apps.flows.di import FlowsDi
from apps.idle_worker.di import IdleWorkerDi
from apps.rag_worker.config import RAGWorkerSettings
from apps.rag_worker.di import RagWorkerDi
from apps.sync.di import SyncDi
from core.config import BaseSettings, get_settings, set_settings
from core.config.loader import load_merged_config
from core.di import DiT, ProcessIdentity, ServiceDi, build_di, process_roots, require_di
from core.files.urls import resolve_files_route_segment

type TaskFunction = Callable[..., Coroutine[object, object, object]]

_SERVICE_APP_MODULES: dict[str, str] = {
    "flows": "apps.flows.main",
    "frontend": "apps.frontend.main",
    "crm": "apps.crm.main",
    "rag": "apps.rag.main",
    "sync": "apps.sync.main",
    "office": "apps.office.main",
    "wiki": "apps.wiki.main",
    "worktracker": "apps.worktracker.main",
    "secrets": "apps.secrets.main",
    "search": "apps.search.main",
    "capability_gateway": "apps.capability_gateway.main",
}

_SERVICE_OF_DI: dict[type[ServiceDi], str] = {
    FlowsDi: "flows",
    SyncDi: "sync",
}


@dataclass(frozen=True, slots=True)
class _WorkerProcess:
    service_name: str
    config_service_name: str
    settings_class: type[BaseSettings]


_WORKER_PROCESSES: dict[type[ServiceDi], _WorkerProcess] = {
    CrmWorkerDi: _WorkerProcess("crm_worker", "crm", CRMSettings),
    RagWorkerDi: _WorkerProcess("rag_worker", "rag_worker", RAGWorkerSettings),
    IdleWorkerDi: _WorkerProcess("idle_worker", "idle_worker", BaseSettings),
}


def task_di_class(task: AsyncTaskiqDecoratedTask[..., object] | TaskFunction) -> type[ServiceDi] | None:
    """Класс DI из аннотации ``di: Di`` задачи; ``None`` — задача без DI."""
    target = task.original_func if isinstance(task, AsyncTaskiqDecoratedTask) else task
    hints: dict[str, object] = typing.get_type_hints(target, include_extras=True)
    annotation = hints.get("di")
    if annotation is None:
        return None
    annotation_args: tuple[object, ...] = typing.get_args(annotation)
    di_class: object = annotation_args[0] if typing.get_origin(annotation) is typing.Annotated else annotation
    if not isinstance(di_class, type) or not issubclass(di_class, ServiceDi):
        raise TypeError(f"{target.__qualname__}: parameter di must be annotated with the process Di alias")
    return di_class


def is_serving(app: FastAPI) -> bool:
    """Lifespan приложения запущен: DI опубликован в ``app.state``."""
    return hasattr(app.state, "di")


def import_service_app(service: str) -> FastAPI | None:
    """ASGI-приложение сервиса; ``None`` — сервис не поднимается внутри процесса тестов.

    Импорт ``apps.<svc>.main`` вызывает ``set_settings`` сервиса, а settings процесса
    тестов один: импорт возвращает прежние.
    """
    module_name = _SERVICE_APP_MODULES.get(service)
    if module_name is None:
        return None
    preserved = get_settings()
    try:
        module = importlib.import_module(module_name)
    finally:
        set_settings(preserved)
    module_attrs: dict[str, object] = vars(module)
    app = module_attrs["app"]
    if not isinstance(app, FastAPI):
        raise TypeError(f"{module_name}.app is {type(app).__qualname__}, expected FastAPI")
    return app


class ServiceProcesses:
    """Приложения сервисов с lifespan и DI воркеров на время сессии тестов."""

    def __init__(self, stack: AsyncExitStack) -> None:
        self._stack: AsyncExitStack = stack
        self._workers: dict[type[ServiceDi], ServiceDi] = {}
        self._app_starts: dict[str, asyncio.Lock] = {}
        self._worker_starts: asyncio.Lock = asyncio.Lock()

    async def app(self, service: str) -> FastAPI:
        app = import_service_app(service)
        if app is None:
            raise RuntimeError(f"service {service} is not hosted in the test process")
        async with self._app_starts.setdefault(service, asyncio.Lock()):
            if not is_serving(app):
                _ = await self._stack.enter_async_context(app.router.lifespan_context(app))
        return app

    async def di(self, di_class: type[DiT]) -> DiT:
        service = _SERVICE_OF_DI.get(di_class)
        if service is not None:
            return require_di(await self.app(service), di_class)
        async with self._worker_starts:
            opened = self._workers.get(di_class)
            if opened is None:
                opened = await self._open_worker(di_class)
                self._workers[di_class] = opened
        if not isinstance(opened, di_class):
            raise TypeError(f"worker DI is {type(opened).__qualname__}, expected {di_class.__qualname__}")
        return opened

    async def _open_worker(self, di_class: type[ServiceDi]) -> ServiceDi:
        worker = _WORKER_PROCESSES.get(di_class)
        if worker is None:
            raise RuntimeError(f"{di_class.__qualname__} is not hosted in the test process")
        settings = worker.settings_class.model_validate(
            load_merged_config(service_name=worker.config_service_name, silent=True)
        )
        identity = ProcessIdentity(
            service_name=worker.service_name,
            files_route_segment=resolve_files_route_segment(worker.service_name),
        )
        return await self._stack.enter_async_context(build_di(di_class, roots=process_roots(settings, identity)))


@pytest_asyncio.fixture(scope="session")
async def service_processes() -> AsyncIterator[ServiceProcesses]:
    async with AsyncExitStack() as stack:
        yield ServiceProcesses(stack)

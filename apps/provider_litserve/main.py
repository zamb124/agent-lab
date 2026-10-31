"""
provider_litserve: платформенный FastAPI shell + LitServe-контур /v1/*.

LitServer собирается внутри lifespan-рецепта ``litserve_workers``: каталог
моделей — снимок ``ready``-строк ``provider_litserve_models`` (Postgres), а не
conf и не pod-local реестр; spawn-воркеры получают его через pickle LitAPI.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Protocol

import litserve as ls
import torch
from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.routing import APIRoute
from litserve.server import response_queue_to_buffer

from apps.provider_litserve.api import models_router
from apps.provider_litserve.catalog import ModelCatalog, sync_seed_entries
from apps.provider_litserve.config import (
    ProviderLitserveServiceSettings,
    get_provider_litserve_settings,
)
from apps.provider_litserve.di import Di, ProviderLitserveDi
from apps.provider_litserve.embedding.api import EmbeddingLitAPI
from apps.provider_litserve.litserve_runtime import (
    ProviderLitserveRuntime,
    provider_litserve_runtime,
)
from apps.provider_litserve.model_ops import run_model_ops_loop
from apps.provider_litserve.openai_server_contracts import (
    build_provider_litserve_v1_models_response,
)
from apps.provider_litserve.provider_litserve_http_schemas import V1ModelsResponseBody
from apps.provider_litserve.reranker.api import RerankerLitAPI
from apps.provider_litserve.stt.api import STTLitAPI
from apps.provider_litserve.tts.api import TTSLitAPI
from apps.provider_litserve.vad.api import VADLitAPI
from apps.provider_litserve.worker_registry import resolved_enabled_workers
from core.app import create_service_app
from core.app.health_payload import build_health_payload
from core.app.server import serve
from core.app.spa import mount_core_frontend, resolve_ui_static_dir
from core.config.models import ProviderLitserveInfraConfig
from core.di import recipe
from core.imports import module_sdk
from core.models.provider_litserve_model import (
    LitserveCatalogEntry,
    LitserveModelKind,
    ProviderLitserveModelPair,
)
from core.request_scope import require_system_admin
from core.utils.background import finish_background_task

UI_PREFIX = "/litserve"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
UI_ROOT_PATH = resolve_ui_static_dir(Path(__file__).parent / "ui")
UI_INDEX_PATH = UI_ROOT_PATH / "index.html"


class _CudaDeviceProperties(Protocol):
    name: str
    total_memory: int


class _CudaRuntime(Protocol):
    def is_available(self) -> bool: ...

    def device_count(self) -> int: ...

    def get_device_properties(self, device: int) -> _CudaDeviceProperties: ...


class ProviderLitserveArgNamespace(argparse.Namespace):
    host: str | None = None
    port: int | None = None


async def _ui_index_handler(di: Di) -> FileResponse:
    _ = await require_system_admin(di.authz_service)
    return FileResponse(UI_INDEX_PATH)


def _ui_health_handler() -> JSONResponse:
    settings = get_provider_litserve_settings()
    return JSONResponse(build_health_payload(settings))


def _cuda_required_for_inference() -> bool:
    cfg = get_provider_litserve_settings().provider_litserve.infra
    if cfg.accelerator == "cuda":
        return True
    if cfg.embedding_accelerator == "cuda" or cfg.rerank_accelerator == "cuda":
        return True
    return False


def _cuda_runtime() -> _CudaRuntime:
    return module_sdk(torch.cuda, _CudaRuntime)


def _inference_health_handler(di: Di) -> JSONResponse:
    settings = get_provider_litserve_settings()
    cfg = settings.provider_litserve.infra
    runtime = di.litserve_runtime
    runtime_started = runtime.inference_started()
    cuda_required = _cuda_required_for_inference()
    cuda_runtime = _cuda_runtime()
    cuda_available = cuda_runtime.is_available()
    device_count = cuda_runtime.device_count() if cuda_available else 0
    devices: list[dict[str, int | str | float]] = []
    if cuda_available:
        for i in range(device_count):
            props = cuda_runtime.get_device_properties(i)
            devices.append(
                {
                    "index": i,
                    "name": props.name,
                    "total_memory_gb": round(props.total_memory / 1024**3, 2),
                }
            )
    ok = runtime_started and (not cuda_required or cuda_available)
    payload = {
        "status": "ok" if ok else "unhealthy",
        "litserve_runtime_started": runtime_started,
        "accelerator": cfg.accelerator,
        "embedding_accelerator": cfg.embedding_accelerator,
        "rerank_accelerator": cfg.rerank_accelerator,
        "enabled_workers": sorted(resolved_enabled_workers(cfg)),
        "cuda_required": cuda_required,
        "cuda_available": cuda_available,
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "cuda_device_count": device_count,
        "cuda_devices": devices,
    }
    return JSONResponse(payload, status_code=200 if ok else 503)


def _register_ui_routes(app: FastAPI) -> None:
    if not UI_INDEX_PATH.exists():
        raise RuntimeError(f"UI entrypoint not found: {UI_INDEX_PATH}")

    router = APIRouter(include_in_schema=False)
    router.add_api_route(UI_PREFIX, _ui_index_handler, methods=["GET"])
    router.add_api_route(f"{UI_PREFIX}/", _ui_index_handler, methods=["GET"])
    router.add_api_route(f"{UI_PREFIX}/health", _ui_health_handler, methods=["GET"])
    router.add_api_route("/health/inference", _inference_health_handler, methods=["GET"])
    app.include_router(router)


def _catalog_pairs(
    catalog: ModelCatalog,
    kind: LitserveModelKind,
) -> list[ProviderLitserveModelPair]:
    entries: Sequence[LitserveCatalogEntry] = catalog.entries(kind)
    return [entry for entry in entries if isinstance(entry, ProviderLitserveModelPair)]


def _register_v1_models_route(server: ls.LitServer, catalog: ModelCatalog) -> None:
    def list_models() -> V1ModelsResponseBody:
        created = int(time.time())
        return build_provider_litserve_v1_models_response(
            embedding_entries=_catalog_pairs(catalog, "embedding"),
            rerank_entries=_catalog_pairs(catalog, "rerank"),
            stt_model_ids=catalog.api_model_ids("stt"),
            tts_model_ids=catalog.api_model_ids("tts"),
            vad_model_ids=catalog.api_model_ids("vad"),
            created=created,
        )

    server.app.add_api_route(
        "/v1/models",
        list_models,
        methods=["GET"],
        dependencies=[Depends(server.setup_auth())],
    )


def _register_v1_inference_health_route(server: ls.LitServer) -> None:
    server.app.add_api_route(
        "/v1/health/inference",
        _inference_health_handler,
        methods=["GET"],
    )


def _merge_litserver_v1_routes(app: FastAPI, lit_app: FastAPI) -> None:
    known = {
        (route.path, tuple(sorted(route.methods or [])))
        for route in app.router.routes
        if isinstance(route, APIRoute)
    }
    for route in lit_app.router.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/v1/"):
            continue
        signature = (route.path, tuple(sorted(route.methods or [])))
        if signature in known:
            continue
        app.router.routes.append(route)
        known.add(signature)


def _build_litserver_apis(
    cfg: ProviderLitserveInfraConfig,
    catalog: ModelCatalog,
) -> list[ls.LitAPI]:
    enabled = resolved_enabled_workers(cfg)
    apis: list[ls.LitAPI] = []
    if "embedding" in enabled:
        apis.append(EmbeddingLitAPI(cfg, catalog))
    if "rerank" in enabled:
        apis.append(RerankerLitAPI(cfg, catalog))
    if "stt" in enabled:
        apis.append(STTLitAPI(cfg, catalog))
    if "tts" in enabled:
        apis.append(TTSLitAPI(cfg, catalog))
    if "vad" in enabled:
        apis.append(VADLitAPI(cfg, catalog))
    if not apis:
        raise RuntimeError("provider_litserve: no LitServe workers enabled")
    return apis


async def _start_litserver_runtime(app: FastAPI, runtime: ProviderLitserveRuntime) -> None:
    lit_server = runtime.server
    if lit_server is None:
        raise RuntimeError("provider_litserve LitServer is not registered")

    manager = lit_server._init_manager(num_api_servers=1)
    lit_server.inference_workers = []
    for lit_api in lit_server.litapi_connector:
        workers = lit_server.launch_inference_worker(lit_api)
        lit_server.inference_workers.extend(workers)
    lit_server.verify_worker_status()

    consumer_id = 0
    setattr(lit_server.app, "response_queue_id", consumer_id)
    setattr(app, "response_queue_id", consumer_id)
    for lit_api in lit_server.litapi_connector:
        if lit_api.spec:
            setattr(lit_api.spec, "response_queue_id", consumer_id)

    task = asyncio.create_task(
        response_queue_to_buffer(
            lit_server._transport,
            lit_server.response_buffer,
            consumer_id,
            lit_server.litapi_connector,
        ),
        name="provider_litserve_response_queue_to_buffer",
    )
    runtime.manager = manager
    runtime.response_task = task


async def _stop_litserver_runtime(runtime: ProviderLitserveRuntime) -> None:
    lit_server = runtime.server
    if lit_server is None:
        raise RuntimeError("provider_litserve LitServer is not registered")
    task = runtime.response_task
    if task is None:
        raise RuntimeError("provider_litserve response task is not started")
    manager = runtime.manager
    if manager is None:
        raise RuntimeError("provider_litserve manager is not started")

    await finish_background_task(task)
    lit_server._perform_graceful_shutdown(manager, {}, "normal")
    runtime.manager = None
    runtime.response_task = None


async def litserve_workers(litserve_runtime: ProviderLitserveRuntime) -> AsyncIterator[None]:
    settings = get_provider_litserve_settings()
    cfg = settings.provider_litserve.infra
    app = litserve_runtime.require_app()

    _ = await sync_seed_entries(cfg)
    catalog = await ModelCatalog.load(enabled_kinds=resolved_enabled_workers(cfg))

    lit_server = ls.LitServer(
        _build_litserver_apis(cfg, catalog),
        accelerator=cfg.accelerator,
        workers_per_device=cfg.workers_per_device,
        timeout=cfg.request_timeout_seconds,
        fast_queue=cfg.fast_queue,
    )
    _register_v1_models_route(lit_server, catalog)
    _register_v1_inference_health_route(lit_server)
    _merge_litserver_v1_routes(app, lit_server.app)
    litserve_runtime.server = lit_server

    ops_task = asyncio.create_task(
        run_model_ops_loop(cfg),
        name="provider_litserve_model_ops",
    )
    started = False
    try:
        await _start_litserver_runtime(app, litserve_runtime)
        started = True
        yield
    finally:
        await finish_background_task(ops_task)
        if started:
            await _stop_litserver_runtime(litserve_runtime)


def build_app() -> FastAPI:
    app = create_service_app(
        "provider_litserve",
        ProviderLitserveServiceSettings,
        ProviderLitserveDi,
        database="shared_url",
        lifecycle=(recipe(litserve_workers),),
        services_spa_index=UI_INDEX_PATH,
        routers=[models_router],
        api_version=None,
        documentation_gateway_prefix="litserve",
        static_mounts=[
            (f"{UI_PREFIX}/ui/static", str(UI_ROOT_PATH), "litserve-ui-static"),
        ],
        mount_repo_documentation=False,
        include_platform_routers=False,
    )
    mount_core_frontend(app)
    _register_ui_routes(app)
    provider_litserve_runtime.attach_app(app)
    return app


app = build_app()


def main() -> None:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--port", type=int, default=None)
    _ = parser.add_argument("--host", type=str, default=None)
    args = ProviderLitserveArgNamespace()
    _ = parser.parse_args(namespace=args)

    settings = get_provider_litserve_settings()
    if args.host is not None:
        settings.server.host = args.host
    if args.port is not None:
        settings.server.port = args.port

    serve("provider_litserve", "apps.provider_litserve.main:app", settings)


if __name__ == "__main__":
    main()

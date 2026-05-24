"""
provider_litserve: платформенный FastAPI shell + LitServe-контур /v1/*.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path

import litserve as ls
import uvicorn
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.routing import APIRoute
from huggingface_hub import scan_cache_dir, snapshot_download
from litserve.server import response_queue_to_buffer
from pydantic import BaseModel, Field

from apps.provider_litserve.config import (
    ProviderLitserveServiceSettings,
    get_provider_litserve_settings,
)
from apps.provider_litserve.container import (
    ProviderLitserveContainer,
    get_provider_litserve_container,
)
from apps.provider_litserve.embedding.api import EmbeddingLitAPI
from apps.provider_litserve.model_registry import (
    ModelKind,
    RegistryModel,
    create_or_replace_model,
    get_model,
    init_registry,
    list_models,
    mark_model_deleted,
    mark_model_status,
    sync_defaults_from_config,
)
from apps.provider_litserve.openai_server_contracts import (
    build_provider_litserve_v1_models_response,
)
from apps.provider_litserve.provider_litserve_http_schemas import V1ModelsResponseBody
from apps.provider_litserve.reranker.api import RerankerLitAPI
from apps.provider_litserve.runtime_models import (
    reload_runtime_catalog_from_sqlite,
    runtime_api_model_ids,
)
from apps.provider_litserve.stt.api import STTLitAPI
from apps.provider_litserve.tts.api import TTSLitAPI
from apps.provider_litserve.vad.api import VADLitAPI
from core.app import create_service_app
from core.app.health_payload import build_health_payload
from core.utils.tokens import get_token_service

SYSTEM_COMPANY_ID = "system"
UI_PREFIX = "/litserve"
UI_API_PREFIX = f"{UI_PREFIX}/api"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
UI_ROOT_PATH = Path(__file__).parent / "ui"
UI_INDEX_PATH = UI_ROOT_PATH / "index.html"
CORE_STATIC_PATH = PROJECT_ROOT / "core" / "frontend" / "static"
_provider_litserve_server: ls.LitServer | None = None
_provider_litserve_manager: ls.LitServerManager | None = None
_provider_litserve_response_task: asyncio.Task[None] | None = None


class ProviderLitserveModelCreateRequest(BaseModel):
    kind: ModelKind = Field(description="embedding | rerank | stt | tts | vad")
    hf_model_id: str
    api_model_id: str


class ProviderLitserveModelListResponse(BaseModel):
    items: list[RegistryModel]


class ProviderLitserveModelDeleteResponse(BaseModel):
    model_id: str


class ProviderLitserveArgNamespace(argparse.Namespace):
    host: str | None = None
    port: int | None = None


def _system_auth_dependency(request: Request) -> None:
    auth_header = request.headers.get("Authorization", "").strip()
    token = request.cookies.get("auth_token", "").strip()
    if auth_header:
        prefix = "Bearer "
        if not auth_header.startswith(prefix):
            raise HTTPException(status_code=401, detail="Invalid Authorization header")
        token = auth_header[len(prefix):].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    token_data = get_token_service().validate_token(token)
    if token_data is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    if token_data.company_id != SYSTEM_COMPANY_ID:
        raise HTTPException(status_code=403, detail="System company required")


def _reload_catalog() -> None:
    cfg = get_provider_litserve_settings().provider_litserve.infra
    _ = reload_runtime_catalog_from_sqlite(cfg)


def _download_model_weights(model_id: str) -> None:
    settings = get_provider_litserve_settings()
    cfg = settings.provider_litserve.infra
    model = get_model(cfg, model_id=model_id)
    mark_model_status(cfg, model_id=model_id, status="downloading")
    try:
        _ = snapshot_download(
            repo_id=model.hf_model_id,
            token=cfg.hf_token,
            local_files_only=False,
        )
    except Exception as exc:
        mark_model_status(cfg, model_id=model_id, status="failed", error=str(exc))
        raise
    mark_model_status(cfg, model_id=model_id, status="ready", error=None)
    _reload_catalog()


def _delete_model_weights(model_id: str) -> None:
    settings = get_provider_litserve_settings()
    cfg = settings.provider_litserve.infra
    model = get_model(cfg, model_id=model_id)
    try:
        cache_info = scan_cache_dir()
        strategy = cache_info.delete_revisions(model.hf_model_id)
        _ = strategy.execute()
    except Exception as exc:
        mark_model_status(cfg, model_id=model_id, status="failed", error=str(exc))
        raise
    mark_model_deleted(cfg, model_id=model_id)
    _reload_catalog()


def _ui_index_handler() -> FileResponse:
    return FileResponse(UI_INDEX_PATH)


def _ui_health_handler() -> JSONResponse:
    settings = get_provider_litserve_settings()
    return JSONResponse(build_health_payload(settings))


def _register_ui_routes(app: FastAPI) -> None:
    if not UI_INDEX_PATH.exists():
        raise RuntimeError(f"UI entrypoint not found: {UI_INDEX_PATH}")

    router = APIRouter(include_in_schema=False)
    router.add_api_route(
        UI_PREFIX,
        _ui_index_handler,
        methods=["GET"],
        dependencies=[Depends(_system_auth_dependency)],
    )
    router.add_api_route(
        f"{UI_PREFIX}/",
        _ui_index_handler,
        methods=["GET"],
        dependencies=[Depends(_system_auth_dependency)],
    )
    router.add_api_route(f"{UI_PREFIX}/health", _ui_health_handler, methods=["GET"])
    app.include_router(router)


def _list_registry_models_handler() -> ProviderLitserveModelListResponse:
    cfg = get_provider_litserve_settings().provider_litserve.infra
    return ProviderLitserveModelListResponse(items=list_models(cfg))


def _add_registry_model_handler(
    payload: ProviderLitserveModelCreateRequest,
    background: BackgroundTasks,
) -> RegistryModel:
    cfg = get_provider_litserve_settings().provider_litserve.infra
    model = create_or_replace_model(
        cfg,
        kind=payload.kind,
        hf_model_id=payload.hf_model_id,
        api_model_id=payload.api_model_id,
    )
    background.add_task(_download_model_weights, model.model_id)
    return model


def _retry_download_handler(model_id: str, background: BackgroundTasks) -> RegistryModel:
    cfg = get_provider_litserve_settings().provider_litserve.infra
    mark_model_status(cfg, model_id=model_id, status="pending", error=None)
    background.add_task(_download_model_weights, model_id)
    return get_model(cfg, model_id=model_id)


def _delete_registry_model_handler(model_id: str, background: BackgroundTasks) -> ProviderLitserveModelDeleteResponse:
    background.add_task(_delete_model_weights, model_id)
    return ProviderLitserveModelDeleteResponse(model_id=model_id)


def _register_model_management_api(app: FastAPI) -> None:
    router = APIRouter(prefix="/litserve/api", tags=["litserve-models"])
    deps = [Depends(_system_auth_dependency)]
    router.add_api_route(
        "/models",
        _list_registry_models_handler,
        methods=["GET"],
        dependencies=deps,
        response_model=ProviderLitserveModelListResponse,
    )
    router.add_api_route(
        "/models",
        _add_registry_model_handler,
        methods=["POST"],
        dependencies=deps,
        response_model=RegistryModel,
    )
    router.add_api_route(
        "/models/{model_id}/retry",
        _retry_download_handler,
        methods=["POST"],
        dependencies=deps,
        response_model=RegistryModel,
    )
    router.add_api_route(
        "/models/{model_id}",
        _delete_registry_model_handler,
        methods=["DELETE"],
        dependencies=deps,
        response_model=ProviderLitserveModelDeleteResponse,
    )
    app.include_router(router)


def _register_v1_models_route(server: ls.LitServer) -> None:
    settings = get_provider_litserve_settings()
    cfg = settings.provider_litserve.infra

    def list_models() -> V1ModelsResponseBody:
        created = int(time.time())
        embedding_model_ids = runtime_api_model_ids("embedding", cfg)
        rerank_model_ids = runtime_api_model_ids("rerank", cfg)
        stt_model_ids = runtime_api_model_ids("stt", cfg)
        tts_model_ids = runtime_api_model_ids("tts", cfg)
        vad_model_ids = runtime_api_model_ids("vad", cfg)
        return build_provider_litserve_v1_models_response(
            embedding_openai_model_id=cfg.embedding_openai_model_id,
            embedding_model_ids=embedding_model_ids,
            embedding_hf_model_id=cfg.embedding_model_id,
            embedding_dimension=settings.rag.embedding.api.dimension,
            embedding_context_length=8192,
            rerank_openai_model_id=cfg.rerank_openai_model_id,
            rerank_model_ids=rerank_model_ids,
            rerank_hf_model_id=cfg.model_id,
            rerank_context_length=8192,
            stt_model_ids=stt_model_ids,
            tts_model_ids=tts_model_ids,
            vad_model_ids=vad_model_ids,
            created=created,
        )

    server.app.add_api_route(
        "/v1/models",
        list_models,
        methods=["GET"],
        dependencies=[Depends(server.setup_auth())],
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


def _register_litserver_v1(app: FastAPI) -> None:
    global _provider_litserve_server

    settings = get_provider_litserve_settings()
    cfg = settings.provider_litserve.infra
    lit_server = ls.LitServer(
        [
            EmbeddingLitAPI(cfg),
            RerankerLitAPI(cfg),
            STTLitAPI(cfg),
            TTSLitAPI(cfg),
            VADLitAPI(cfg),
        ],
        accelerator=cfg.accelerator,
        workers_per_device=cfg.workers_per_device,
        timeout=cfg.request_timeout_seconds,
        fast_queue=cfg.fast_queue,
    )
    _register_v1_models_route(lit_server)
    _merge_litserver_v1_routes(app, lit_server.app)
    _provider_litserve_server = lit_server


async def _bootstrap_runtime_registry() -> None:
    settings = get_provider_litserve_settings()
    cfg = settings.provider_litserve.infra
    init_registry(cfg)
    sync_defaults_from_config(cfg)
    _ = reload_runtime_catalog_from_sqlite(cfg)


async def _start_litserver_runtime(app: FastAPI) -> None:
    global _provider_litserve_manager, _provider_litserve_response_task

    lit_server = _provider_litserve_server
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
    _provider_litserve_manager = manager
    _provider_litserve_response_task = task


async def _stop_litserver_runtime() -> None:
    global _provider_litserve_manager, _provider_litserve_response_task

    lit_server = _provider_litserve_server
    if lit_server is None:
        raise RuntimeError("provider_litserve LitServer is not registered")
    task = _provider_litserve_response_task
    if task is None:
        raise RuntimeError("provider_litserve response task is not started")
    manager = _provider_litserve_manager
    if manager is None:
        raise RuntimeError("provider_litserve manager is not started")

    _ = task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    lit_server._perform_graceful_shutdown(manager, {}, "normal")
    _provider_litserve_manager = None
    _provider_litserve_response_task = None


async def _on_startup(
    app: FastAPI,
    _container: ProviderLitserveContainer,
    _settings: ProviderLitserveServiceSettings,
) -> None:
    await _bootstrap_runtime_registry()
    await _start_litserver_runtime(app)


async def _on_shutdown(_app: FastAPI, _container: ProviderLitserveContainer) -> None:
    await _stop_litserver_runtime()


def build_app() -> FastAPI:
    app = create_service_app(
        service_name="provider_litserve",
        settings_class=ProviderLitserveServiceSettings,
        get_container=get_provider_litserve_container,
        services_spa_index=UI_INDEX_PATH,
        routers=[],
        on_startup=_on_startup,
        on_shutdown=_on_shutdown,
        include_crud_routers=False,
        documentation_gateway_prefix="litserve",
        static_mounts=[
            ("/static/core", str(CORE_STATIC_PATH), "litserve-core-static"),
            (f"{UI_PREFIX}/ui/static", str(UI_ROOT_PATH), "litserve-ui-static"),
        ],
        mount_repo_documentation=False,
    )
    _register_ui_routes(app)
    _register_model_management_api(app)
    _register_litserver_v1(app)
    return app


app = build_app()


def main() -> None:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--port", type=int, default=None)
    _ = parser.add_argument("--host", type=str, default=None)
    args = ProviderLitserveArgNamespace()
    _ = parser.parse_args(namespace=args)

    settings = get_provider_litserve_settings()
    host = args.host if args.host is not None else settings.server.host
    port = args.port if args.port is not None else settings.server.port

    uvicorn.run(
        "apps.provider_litserve.main:app",
        host=host,
        port=port,
        reload=settings.server.debug,
    )


if __name__ == "__main__":
    main()

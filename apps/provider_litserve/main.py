"""
provider_litserve: платформенный FastAPI shell + LitServe-контур /v1/*.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path
from typing import Any, Literal

import litserve as ls
import torch
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.routing import APIRoute
from litserve.server import response_queue_to_buffer
from pydantic import BaseModel, Field

from apps.provider_litserve.config import (
    ProviderLitserveServiceSettings,
    get_provider_litserve_settings,
)
from apps.provider_litserve.container import get_provider_litserve_container
from apps.provider_litserve.embedding.api import EmbeddingLitAPI
from apps.provider_litserve.llm.local_causal_lm import ensure_local_causal_lm
from apps.provider_litserve.markdown_format.api import MarkdownFormatLitAPI
from apps.provider_litserve.model_registry import (
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
from apps.provider_litserve.reranker.api import RerankerLitAPI
from apps.provider_litserve.runtime_models import (
    allowed_api_model_ids,
    reload_runtime_catalog_from_sqlite,
    resolve_hf_model_id,
    runtime_api_model_ids,
)
from apps.provider_litserve.shared import resolve_torch_device
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


class ProviderLitserveModelCreateRequest(BaseModel):
    kind: Literal["llm", "embedding", "rerank", "stt", "tts", "vad"] = Field(
        description="llm | embedding | rerank | stt | tts | vad"
    )
    hf_model_id: str
    api_model_id: str


def _serialize_model(model) -> dict[str, Any]:
    return {
        "model_id": model.model_id,
        "kind": model.kind,
        "hf_model_id": model.hf_model_id,
        "api_model_id": model.api_model_id,
        "status": model.status,
        "error": model.error,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
    }


def _model_to_payload() -> list[dict[str, Any]]:
    cfg = get_provider_litserve_settings().provider_litserve.infra
    return [_serialize_model(model) for model in list_models(cfg)]


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
    reload_runtime_catalog_from_sqlite(cfg)


def _download_model_weights(model_id: str) -> None:
    settings = get_provider_litserve_settings()
    cfg = settings.provider_litserve.infra
    model = get_model(cfg, model_id=model_id)
    mark_model_status(cfg, model_id=model_id, status="downloading")
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(
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
        from huggingface_hub import scan_cache_dir

        cache_info = scan_cache_dir()
        strategy = cache_info.delete_revisions(model.hf_model_id)
        strategy.execute()
    except Exception as exc:
        mark_model_status(cfg, model_id=model_id, status="failed", error=str(exc))
        raise
    mark_model_deleted(cfg, model_id=model_id)
    _reload_catalog()


class ChatCompletionsLitAPI(ls.LitAPI):
    """Локальный `/v1/chat/completions` через встроенный LitServe OpenAISpec."""

    def __init__(self) -> None:
        super().__init__(spec=ls.OpenAISpec())
        self._device: str = "cpu"
        self._max_new_tokens: int = 4096
        self._hf_token: str | None = None
        self._infra = get_provider_litserve_settings().provider_litserve.infra

    def setup(self, device) -> None:
        settings = get_provider_litserve_settings()
        infra = settings.provider_litserve.infra
        self._device = str(device) if device else resolve_torch_device(infra)
        self._hf_token = infra.hf_token
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "Локальный chat backend: установите зависимости transformers (uv sync --group reranker-model)"
            ) from exc
        _ = AutoModelForCausalLM
        _ = AutoTokenizer

    def decode_request(self, request):
        return request.model_dump(exclude_none=True)

    def predict(self, request):
        body = dict(request)
        requested_model = str(body.get("model", "")).strip()
        allowed_ids = allowed_api_model_ids("llm", self._infra)
        req_lower = requested_model.lower()
        if not any(a.lower() == req_lower for a in allowed_ids):
            raise HTTPException(
                status_code=422,
                detail={
                    "reason": "unknown_chat_model",
                    "model": requested_model,
                    "allowed": sorted(allowed_ids),
                },
            )
        hf_model_id = resolve_hf_model_id("llm", requested_model, self._infra)
        if hf_model_id is None:
            raise HTTPException(status_code=422, detail={"reason": "unknown_chat_model", "model": requested_model})
        tokenizer, model = ensure_local_causal_lm(
            hf_model_id=hf_model_id,
            device=self._device,
            hf_token=self._hf_token,
        )

        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            raise HTTPException(status_code=422, detail={"reason": "messages_required"})

        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        model_inputs = tokenizer(prompt, return_tensors="pt").to(self._device)
        input_tokens = int(model_inputs["input_ids"].shape[1])
        with torch.no_grad():
            generated = model.generate(
                **model_inputs,
                max_new_tokens=self._max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
        output_ids = generated[0][input_tokens:]
        content = tokenizer.decode(output_ids, skip_special_tokens=True).strip()
        completion_tokens = int(output_ids.shape[0])
        encoded: dict[str, Any] = {
            "role": "assistant",
            "content": content,
            "prompt_tokens": input_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": input_tokens + completion_tokens,
        }
        yield encoded


def _register_ui_routes(app: FastAPI) -> None:
    if not UI_INDEX_PATH.exists():
        raise RuntimeError(f"UI entrypoint not found: {UI_INDEX_PATH}")

    router = APIRouter(include_in_schema=False)

    @router.get(UI_PREFIX, dependencies=[Depends(_system_auth_dependency)])
    def ui_index() -> FileResponse:
        return FileResponse(UI_INDEX_PATH)

    @router.get(f"{UI_PREFIX}/", dependencies=[Depends(_system_auth_dependency)])
    def ui_index_trailing() -> FileResponse:
        return FileResponse(UI_INDEX_PATH)

    @router.get(f"{UI_PREFIX}/health")
    def ui_health() -> JSONResponse:
        settings = get_provider_litserve_settings()
        return JSONResponse(build_health_payload(settings))

    app.include_router(router)


def _register_model_management_api(app: FastAPI) -> None:
    router = APIRouter(prefix="/litserve/api", tags=["litserve-models"])
    deps = [Depends(_system_auth_dependency)]

    @router.get("/models", dependencies=deps)
    def list_registry_models() -> dict[str, Any]:
        return {"items": _model_to_payload()}

    @router.post("/models", dependencies=deps)
    def add_registry_model(payload: ProviderLitserveModelCreateRequest, background: BackgroundTasks) -> dict[str, Any]:
        cfg = get_provider_litserve_settings().provider_litserve.infra
        model = create_or_replace_model(
            cfg,
            kind=payload.kind,
            hf_model_id=payload.hf_model_id,
            api_model_id=payload.api_model_id,
        )
        background.add_task(_download_model_weights, model.model_id)
        return _serialize_model(model)

    @router.post("/models/{model_id}/retry", dependencies=deps)
    def retry_download(model_id: str, background: BackgroundTasks) -> dict[str, Any]:
        cfg = get_provider_litserve_settings().provider_litserve.infra
        mark_model_status(cfg, model_id=model_id, status="pending", error=None)
        background.add_task(_download_model_weights, model_id)
        return _serialize_model(get_model(cfg, model_id=model_id))

    @router.delete("/models/{model_id}", dependencies=deps)
    def delete_registry_model(model_id: str, background: BackgroundTasks) -> dict[str, Any]:
        background.add_task(_delete_model_weights, model_id)
        return {"model_id": model_id}

    app.include_router(router)


def _register_v1_models_route(server: ls.LitServer) -> None:
    settings = get_provider_litserve_settings()
    cfg = settings.provider_litserve.infra

    def list_models() -> dict[str, Any]:
        created = int(time.time())
        chat_model_ids = runtime_api_model_ids("llm", cfg)
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
            chat_model_ids=chat_model_ids,
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
    settings = get_provider_litserve_settings()
    cfg = settings.provider_litserve.infra
    lit_server = ls.LitServer(
        [
            EmbeddingLitAPI(cfg),
            RerankerLitAPI(cfg),
            ChatCompletionsLitAPI(),
            MarkdownFormatLitAPI(cfg),
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
    app.state.provider_litserve_server = lit_server


async def _bootstrap_runtime_registry() -> None:
    settings = get_provider_litserve_settings()
    cfg = settings.provider_litserve.infra
    init_registry(cfg)
    sync_defaults_from_config(cfg)
    reload_runtime_catalog_from_sqlite(cfg)


async def _start_litserver_runtime(app: FastAPI) -> None:
    lit_server: ls.LitServer = app.state.provider_litserve_server
    manager = lit_server._init_manager(num_api_servers=1)
    lit_server.inference_workers = []
    for lit_api in lit_server.litapi_connector:
        workers = lit_server.launch_inference_worker(lit_api)
        lit_server.inference_workers.extend(workers)
    lit_server.verify_worker_status()

    consumer_id = 0
    lit_server.app.response_queue_id = consumer_id
    app.response_queue_id = consumer_id
    for lit_api in lit_server.litapi_connector:
        if lit_api.spec:
            lit_api.spec.response_queue_id = consumer_id

    task = asyncio.create_task(
        response_queue_to_buffer(
            lit_server._transport,
            lit_server.response_buffer,
            consumer_id,
            lit_server.litapi_connector,
        ),
        name="provider_litserve_response_queue_to_buffer",
    )
    app.state.provider_litserve_manager = manager
    app.state.provider_litserve_response_task = task


async def _stop_litserver_runtime(app: FastAPI) -> None:
    lit_server: ls.LitServer = app.state.provider_litserve_server
    task = getattr(app.state, "provider_litserve_response_task", None)
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    manager = getattr(app.state, "provider_litserve_manager", None)
    if manager is not None:
        lit_server._perform_graceful_shutdown(manager, {}, "normal")


async def _on_startup(app: FastAPI, container, settings) -> None:
    _ = container
    _ = settings
    await _bootstrap_runtime_registry()
    await _start_litserver_runtime(app)


async def _on_shutdown(app: FastAPI, container) -> None:
    _ = container
    await _stop_litserver_runtime(app)


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
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--host", type=str, default=None)
    args = parser.parse_args()

    settings = get_provider_litserve_settings()
    host = args.host if args.host is not None else settings.server.host
    port = args.port if args.port is not None else settings.server.port

    import uvicorn

    uvicorn.run(
        "apps.provider_litserve.main:app",
        host=host,
        port=port,
        reload=settings.server.debug,
    )


if __name__ == "__main__":
    main()

from collections.abc import Iterator, Sequence
from typing import Literal, Protocol

from fastapi import FastAPI

from core.types import JsonValue

type Accelerator = Literal["cpu", "cuda", "mps", "auto"]
type DeviceSelection = int | Literal["auto"]


class LitSpec:
    response_queue_id: int
    api_path: str
    stream: bool


class OpenAISpec(LitSpec): ...


class LitDependency(Protocol):
    def __call__(self) -> JsonValue: ...


class LitTransport: ...


class LitServerManager: ...


class LitWorkerProcess: ...


class ResponseBufferItem: ...


class LitAPI:
    spec: LitSpec | None
    api_path: str
    stream: bool
    max_batch_size: int
    batch_timeout: float
    enable_async: bool

    def __init__(
        self,
        max_batch_size: int = ...,
        batch_timeout: float = ...,
        api_path: str = ...,
        stream: bool = ...,
        spec: LitSpec | None = ...,
        enable_async: bool = ...,
    ) -> None: ...


class LitAPIConnector:
    lit_apis: list[LitAPI]

    def __iter__(self) -> Iterator[LitAPI]: ...


class LitServer:
    app: FastAPI
    litapi_connector: LitAPIConnector
    lit_api: LitAPI | list[LitAPI]
    inference_workers: list[LitWorkerProcess]
    response_buffer: dict[str, ResponseBufferItem]
    _transport: LitTransport

    def __init__(
        self,
        lit_api: LitAPI | Sequence[LitAPI],
        accelerator: Accelerator = ...,
        devices: DeviceSelection = ...,
        workers_per_device: int = ...,
        timeout: float | bool = ...,
        fast_queue: bool = ...,
        disable_openapi_url: bool = ...,
    ) -> None: ...

    def setup_auth(self) -> LitDependency: ...
    def _init_manager(self, num_api_servers: int) -> LitServerManager: ...
    def launch_inference_worker(self, lit_api: LitAPI) -> list[LitWorkerProcess]: ...
    def verify_worker_status(self) -> None: ...
    def _perform_graceful_shutdown(
        self,
        manager: LitServerManager,
        uvicorn_workers: dict[str, LitWorkerProcess],
        shutdown_reason: str = ...,
    ) -> None: ...

"""
ASGI-заглушка POST ``/v1/rerank`` с подменяемым upstream через ``dependency_overrides``.

Имитирует проксирование тела запроса к бэкенду реранка (ответ с полем ``scores``).
"""

from __future__ import annotations

from typing import Annotated, Protocol

import httpx
from fastapi import Depends, FastAPI, Request, Response


class RerankUpstreamPort(Protocol):
    """Бэкенд реранка: принимает сырое тело POST, возвращает HTTP-ответ."""

    async def post_predict(self, body: bytes, content_type: str) -> httpx.Response:
        ...


def get_rerank_upstream() -> RerankUpstreamPort:
    raise RuntimeError("Задайте app.dependency_overrides[get_rerank_upstream]")


async def _proxy_rerank_to_upstream(request: Request, upstream: RerankUpstreamPort) -> Response:
    body = await request.body()
    ct = request.headers.get("content-type", "application/json")
    r = await upstream.post_predict(body, ct)
    out_ct = r.headers.get("content-type", "application/json")
    return Response(content=r.content, status_code=r.status_code, media_type=out_ct)


def create_v1_rerank_stub_app() -> FastAPI:
    app = FastAPI()

    @app.post("/v1/rerank")
    async def post_v1_rerank(
        request: Request,
        upstream: Annotated[RerankUpstreamPort, Depends(get_rerank_upstream)],
    ) -> Response:
        return await _proxy_rerank_to_upstream(request, upstream)

    return app

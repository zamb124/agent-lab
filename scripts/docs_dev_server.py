"""
Локальный preview документации в топологии продакшена:
  /documentation/  → documentation-dist/
  /static/core/    → core/frontend/static/
  /frontend/, /flows/, /api/ → proxy на запущенные сервисы

Zensical serve не монтирует /static/core, поэтому Ask AI получает HTML вместо JS
(MIME module error). Этот сервер повторяет mount платформы.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTATION_DIST = REPO_ROOT / "documentation-dist"
CORE_STATIC = REPO_ROOT / "core" / "frontend" / "static"
CONF_PATHS = (REPO_ROOT / "conf.local.json", REPO_ROOT / "conf.json")


def _load_server_urls() -> tuple[str, str]:
    merged: dict[str, object] = {}
    for path in CONF_PATHS:
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"conf root must be object: {path}")
        server = payload.get("server")
        if isinstance(server, dict):
            merged.update(server)
    frontend = merged.get("frontend_service_url")
    flows = merged.get("flows_service_url")
    if not isinstance(frontend, str) or not frontend.strip():
        raise ValueError("server.frontend_service_url обязателен в conf.json")
    if not isinstance(flows, str) or not flows.strip():
        raise ValueError("server.flows_service_url обязателен в conf.json")
    return frontend.rstrip("/"), flows.rstrip("/")


def _proxy_prefixes(frontend_url: str, flows_url: str) -> dict[str, str]:
    return {
        "/frontend": frontend_url,
        "/flows": flows_url,
        "/api": frontend_url,
    }


def build_app() -> FastAPI:
    if not DOCUMENTATION_DIST.is_dir():
        raise FileNotFoundError(f"Нет {DOCUMENTATION_DIST}: сначала выполните make doc")
    if not CORE_STATIC.is_dir():
        raise FileNotFoundError(f"Нет {CORE_STATIC}")

    frontend_url, flows_url = _load_server_urls()
    prefixes = _proxy_prefixes(frontend_url, flows_url)
    app = FastAPI(title="docs-dev-server")

    @app.get("/")
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/documentation/", status_code=307)

    async def proxy_platform(request: Request) -> Response:
        full_path = request.url.path
        upstream_base: str | None = None
        for prefix, base in prefixes.items():
            if full_path == prefix or full_path.startswith(f"{prefix}/"):
                upstream_base = base
                break
        if upstream_base is None:
            return Response(status_code=404, content="Not Found")

        upstream_url = f"{upstream_base}{full_path}"
        if request.url.query:
            upstream_url = f"{upstream_url}?{request.url.query}"

        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower() not in {"host", "content-length"}
        }
        body = await request.body()
        async with httpx.AsyncClient(follow_redirects=False, timeout=120.0) as client:
            upstream = await client.request(
                request.method,
                upstream_url,
                headers=headers,
                content=body,
            )
        excluded = {
            "content-encoding",
            "transfer-encoding",
            "content-length",
            "connection",
        }
        response_headers = {
            key: value
            for key, value in upstream.headers.items()
            if key.lower() not in excluded
        }
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers=response_headers,
            media_type=upstream.headers.get("content-type"),
        )

    for prefix in prefixes:
        app.add_api_route(
            prefix,
            proxy_platform,
            methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        )
        app.add_api_route(
            f"{prefix}/{{path:path}}",
            proxy_platform,
            methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        )

    app.mount(
        "/static/core",
        StaticFiles(directory=str(CORE_STATIC), check_dir=True),
        name="docs-dev-static-core",
    )
    app.mount(
        "/documentation",
        StaticFiles(directory=str(DOCUMENTATION_DIST), html=True, check_dir=True),
        name="docs-dev-documentation",
    )
    return app


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Docs preview with /documentation + /static/core + API proxy",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    frontend_url, flows_url = _load_server_urls()
    print(f"docs-dev-server: http://{args.host}:{args.port}/documentation/")
    print(f"  static: /static/core → {CORE_STATIC}")
    print(f"  proxy /frontend → {frontend_url}")
    print(f"  proxy /flows → {flows_url}")
    print("  Нужны запущенные frontend и flows (make app).")
    uvicorn.run(build_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

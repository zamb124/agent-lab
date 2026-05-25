"""
Публичный маршрут раздачи единого реестра типов файлов для всех SPA.

Данные формируются из core.files.types при старте и кешируются в памяти.
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from core.files.types import FileTypesPayload, build_file_types_payload

_CACHED_PAYLOAD: FileTypesPayload = build_file_types_payload()


def register_platform_file_types_route(app: FastAPI) -> None:
    """Регистрирует GET /api/platform/file-types на приложении."""

    async def get_file_types() -> JSONResponse:
        return JSONResponse(
            content=_CACHED_PAYLOAD,
            headers={"Cache-Control": "public, max-age=3600"},
        )

    app.add_api_route("/api/platform/file-types", get_file_types, methods=["GET"])

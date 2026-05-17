"""
Публичный маршрут раздачи единого реестра типов файлов для всех SPA.

Данные формируются из core.files.types при старте и кешируются в памяти.
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from core.files.types import ALL_CATEGORIES, FILE_TYPE_REGISTRY


def _build_cached_payload() -> dict[str, object]:
    return {
        "categories": [c.value for c in ALL_CATEGORIES],
        "registry": [
            {
                "extension": entry.extension,
                "mime_types": list(entry.mime_types),
                "category": entry.category.value,
            }
            for entry in FILE_TYPE_REGISTRY
        ],
    }


_CACHED_PAYLOAD = _build_cached_payload()


def register_platform_file_types_route(app: FastAPI) -> None:
    """Регистрирует GET /api/platform/file-types на приложении."""

    @app.get("/api/platform/file-types")
    async def get_file_types() -> JSONResponse:
        return JSONResponse(
            content=_CACHED_PAYLOAD,
            headers={"Cache-Control": "public, max-age=3600"},
        )

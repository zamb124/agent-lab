"""
Публичные маршруты загрузки JSON-переводов для SPA на всех сервисах.
"""

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

_SUPPORTED_LOCALES = frozenset({"ru", "en"})


def register_platform_i18n_routes(app: FastAPI, project_root: Path) -> None:
    """
    Регистрирует GET /api/i18n/{locale} — объединённые namespace из
    core/i18n/translations/{locale}/*.json (файлы с префиксом _ пропускаются).
    """

    translations_root = project_root / "core" / "i18n" / "translations"

    @app.get("/api/i18n/{locale}")
    async def get_translations(locale: str) -> JSONResponse:
        if locale not in _SUPPORTED_LOCALES:
            raise HTTPException(status_code=400, detail="Unsupported locale")

        translations_path = translations_root / locale
        if not translations_path.is_dir():
            raise HTTPException(
                status_code=404,
                detail=f"Translations not found for locale: {locale}",
            )

        translations: dict[str, Any] = {}
        for file_path in sorted(translations_path.glob("*.json")):
            namespace = file_path.stem
            if namespace.startswith("_"):
                continue
            with open(file_path, encoding="utf-8") as f:
                translations[namespace] = json.load(f)

        return JSONResponse(content=translations)

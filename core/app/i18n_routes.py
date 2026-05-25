"""Публичные маршруты загрузки JSON-переводов для SPA на всех сервисах."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from core.types import JsonObject, parse_json_object

_SUPPORTED_LOCALES = frozenset({"ru", "en"})


def register_platform_i18n_routes(app: FastAPI, project_root: Path) -> None:
    """
    Регистрирует GET /api/i18n/{locale} — объединённые namespace из
    core/i18n/translations/{locale}/*.json (файлы с префиксом _ пропускаются).
    """

    translations_root = project_root / "core" / "i18n" / "translations"

    async def get_translations(locale: str) -> JSONResponse:
        if locale not in _SUPPORTED_LOCALES:
            raise HTTPException(status_code=400, detail="Unsupported locale")

        translations_path = translations_root / locale
        if not translations_path.is_dir():
            raise HTTPException(
                status_code=404,
                detail=f"Translations not found for locale: {locale}",
            )

        translations: JsonObject = {}
        for file_path in sorted(translations_path.glob("*.json")):
            namespace = file_path.stem
            if namespace.startswith("_"):
                continue
            translations[namespace] = parse_json_object(
                file_path.read_text(encoding="utf-8"),
                f"i18n.{locale}.{namespace}",
            )

        return JSONResponse(content=translations)

    app.add_api_route("/api/i18n/{locale}", get_translations, methods=["GET"])

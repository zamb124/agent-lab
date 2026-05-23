"""
Извлекает OpenAPI схемы из сервисов и фильтрует по тегу 'public'.

Для каждого сервиса:
1. Импортирует FastAPI app
2. Вызывает app.openapi() для получения полной схемы
3. Фильтрует пути, оставляя только операции с тегом 'public'
4. Сохраняет отфильтрованную схему в docs/openapi/{service}.json
"""
from __future__ import annotations

import importlib
import json
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Список сервисов для обработки: (имя_сервиса, import_path)
SERVICES = [
    ("flows", "apps.flows.main:app"),
    ("crm", "apps.crm.main:app"),
    ("rag", "apps.rag.main:app"),
    ("sync", "apps.sync.main:app"),
    ("frontend", "apps.frontend.main:app"),
]


def import_app(import_path: str):
    """
    Динамически импортирует FastAPI app по пути модуля:объект.

    Args:
        import_path: Путь в формате "module.submodule:app"

    Returns:
        FastAPI app instance
    """
    module_path, object_name = import_path.split(":")
    module = importlib.import_module(module_path)
    return getattr(module, object_name)


def filter_public_paths(openapi_schema: dict) -> dict:
    """
    Фильтрует OpenAPI схему, оставляя только операции с тегом 'public'.

    Args:
        openapi_schema: Полная OpenAPI схема из app.openapi()

    Returns:
        Отфильтрованная схема с только публичными операциями
    """
    filtered_schema = openapi_schema.copy()
    filtered_paths = {}

    paths = openapi_schema.get("paths", {})

    for path, methods in paths.items():
        filtered_methods = {}

        for method, operation in methods.items():
            # Получаем теги операции
            tags = operation.get("tags", [])

            # Если есть тег 'public', оставляем операцию
            if "public" in tags:
                filtered_methods[method] = operation
                logger.debug(f"✓ Публичный API: {method.upper()} {path} (tags: {tags})")

        # Если есть хотя бы один публичный метод, оставляем путь
        if filtered_methods:
            filtered_paths[path] = filtered_methods

    filtered_schema["paths"] = filtered_paths

    # Обновляем статистику тегов
    all_tags = set()
    for path, methods in filtered_paths.items():
        for method, operation in methods.items():
            all_tags.update(operation.get("tags", []))

    # Убираем 'public' из списка тегов для чистоты
    all_tags.discard("public")

    if all_tags:
        filtered_schema["tags"] = [
            {"name": tag, "description": f"Public API endpoints for {tag}"}
            for tag in sorted(all_tags)
        ]
    else:
        filtered_schema.pop("tags", None)

    logger.info(f"Отфильтровано: {len(filtered_paths)} путей с публичными операциями")

    return filtered_schema


def extract_service_openapi(service_name: str, app_path: str) -> dict:
    """
    Извлекает и фильтрует OpenAPI схему для сервиса.

    Args:
        service_name: Имя сервиса (flows, crm, и т.д.)
        app_path: Import path для FastAPI app

    Returns:
        Отфильтрованная OpenAPI схема
    """
    logger.info(f"Извлечение OpenAPI для сервиса: {service_name}")

    try:
        app = import_app(app_path)
        full_schema = app.openapi()

        # Фильтруем по тегу 'public'
        filtered_schema = filter_public_paths(full_schema)

        # Добавляем информацию о сервисе
        if "info" in filtered_schema:
            filtered_schema["info"]["title"] = f"{service_name.title()} Public API"
            filtered_schema["info"]["x-service"] = service_name

        return filtered_schema

    except Exception as e:
        logger.error(f"Ошибка извлечения OpenAPI для {service_name}: {e}", exc_info=True)
        raise


def write_service_openapi(service_name: str, app_path: str, output_file: Path) -> None:
    """Пишет OpenAPI одного сервиса. Вызывается в отдельном процессе."""
    schema = extract_service_openapi(service_name, app_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(f"✅ Сохранена схема для {service_name}: {output_file}")


def _run_service_child(script_path: Path, service_name: str, app_path: str, output_file: Path) -> None:
    """Изоляция важна: сервисы на импорте настраивают logging и регистрируют глобальные хуки."""
    subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--service",
            service_name,
            "--app-path",
            app_path,
            "--output",
            str(output_file),
        ],
        check=True,
    )


def main() -> None:
    """Извлекает OpenAPI схемы для всех сервисов."""
    if "--service" in sys.argv:
        service_name = sys.argv[sys.argv.index("--service") + 1]
        app_path = sys.argv[sys.argv.index("--app-path") + 1]
        output_file = Path(sys.argv[sys.argv.index("--output") + 1])
        write_service_openapi(service_name, app_path, output_file)
        return

    root = Path(__file__).resolve().parents[1]
    output_dir = root / "docs" / "openapi"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Директория для OpenAPI схем: {output_dir}")

    script_path = Path(__file__).resolve()
    for service_name, app_path in SERVICES:
        output_file = output_dir / f"{service_name}.json"
        _run_service_child(script_path, service_name, app_path, output_file)

    logger.info("Извлечение OpenAPI схем завершено")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s"
    )
    main()

"""
Конвертирует OpenAPI JSON в Markdown с интерактивным Swagger UI.

Для каждого сервиса:
1. Читает OpenAPI JSON из docs/openapi/{service}.json
2. Генерирует Markdown с:
   - Заголовком и описанием (из intro.md если есть)
   - Интерактивным Swagger UI (embedded)
   - Списком эндпоинтов с описаниями
   - Примерами запросов/ответов
3. Сохраняет в build/documentation-{lang}/api/{service}/index.md
"""

from __future__ import annotations

import html
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_CRM_BRAND_RE = re.compile(r"(?<![A-Za-z0-9])CRM(?![A-Za-z0-9])")


def _brand_display_text(value: str) -> str:
    """Пользовательское название продукта в документации без переименования API-контрактов."""
    return _CRM_BRAND_RE.sub("NetWorkle", value)

# Локализации заголовков
LOCALIZATIONS = {
    "ru": {
        "api_title": "API",
        "endpoints": "Эндпоинты",
        "interactive": "Интерактивная документация",
        "method": "Метод",
        "description": "Описание",
        "request": "Запрос",
        "response": "Ответ",
        "no_endpoints": "Нет публичных эндпоинтов",
    },
    "en": {
        "api_title": "API",
        "endpoints": "Endpoints",
        "interactive": "Interactive Documentation",
        "method": "Method",
        "description": "Description",
        "request": "Request",
        "response": "Response",
        "no_endpoints": "No public endpoints",
    },
}


def get_localization(lang: str, key: str) -> str:
    """Получает локализованную строку."""
    return LOCALIZATIONS.get(lang, LOCALIZATIONS["en"]).get(key, key)


def read_intro(service_name: str, lang: str) -> str | None:
    """
    Читает ручное описание сервиса из docs/api/{service}/intro.md или intro.{lang}.md.

    Args:
        service_name: Имя сервиса
        lang: Код языка (ru/en)

    Returns:
        Содержимое файла или None
    """
    root = Path(__file__).resolve().parents[1]

    # Пытаемся прочитать intro.{lang}.md, затем intro.md
    for filename in [f"intro.{lang}.md", "intro.md"]:
        intro_file = root / "docs" / "api" / service_name / filename
        if intro_file.exists():
            return intro_file.read_text(encoding="utf-8")

    return None


def generate_swagger_ui_embed(openapi_schema: dict, service_name: str) -> str:
    """
    Генерирует ссылки на встроенную документацию сервиса.

    Args:
        openapi_schema: OpenAPI схема
        service_name: Имя сервиса

    Returns:
        Markdown строка со ссылками на интерактивную документацию
    """
    # Порты сервисов
    service_ports = {
        "flows": 8001,
        "frontend": 8002,
        "crm": 8003,
        "rag": 8004,
        "sync": 8005,
    }

    port = service_ports.get(service_name, 8001)

    return f"""
!!! info

    Интерактивная документация сервиса:

    - [Swagger UI](https://humanitec.ru:{port}/docs)
    - [ReDoc](https://humanitec.ru:{port}/redoc)

    Доступно полное описание всех эндпоинтов с возможностью тестирования.
"""


def resolve_schema_ref(schema: dict | str, openapi_schema: dict) -> dict:
    """
    Разворачивает $ref ссылки в реальные схемы.

    Args:
        schema: Объект схемы или строка $ref
        openapi_schema: Полная OpenAPI схема

    Returns:
        Развёрнутая схема
    """
    if isinstance(schema, str):
        if schema.startswith("#/components/schemas/"):
            schema_name = schema.split("/")[-1]
            components = openapi_schema.get("components", {})
            schemas = components.get("schemas", {})
            return schemas.get(schema_name, {})
        return {}

    if isinstance(schema, dict):
        if "$ref" in schema:
            ref = schema["$ref"]
            resolved = resolve_schema_ref(ref, openapi_schema)
            # Копируем остальные свойства из исходной схемы
            result = resolved.copy()
            for key, value in schema.items():
                if key != "$ref":
                    result[key] = value
            return result

        # Рекурсивно разворачиваем вложенные объекты
        result = {}
        for key, value in schema.items():
            if key in ["allOf", "anyOf", "oneOf"]:
                # Для композиции схем берём первый элемент
                if isinstance(value, list) and value:
                    result[key] = [resolve_schema_ref(item, openapi_schema) for item in value]
                else:
                    result[key] = value
            elif isinstance(value, dict):
                result[key] = resolve_schema_ref(value, openapi_schema)
            elif isinstance(value, list):
                result[key] = [
                    resolve_schema_ref(item, openapi_schema)
                    if isinstance(item, (dict, str))
                    else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    return schema


def generate_endpoint_markdown(
    path: str, method: str, operation: dict, lang: str, openapi_schema: dict | None = None
) -> str:
    """
    Генерирует Markdown для одного эндпоинта.

    Args:
        path: Путь эндпоинта
        method: HTTP метод
        operation: Операция из OpenAPI
        lang: Код языка
        openapi_schema: Полная OpenAPI схема для разворачивания $ref

    Returns:
        Markdown строка
    """
    loc = LOCALIZATIONS.get(lang, LOCALIZATIONS["en"])

    method_upper = method.upper()
    method_class = method_upper.lower()

    summary = _brand_display_text(operation.get("summary", operation.get("description", "")))
    description = _brand_display_text(operation.get("description", ""))

    md = f'### <span class="docs-http-method docs-method-{method_class}">{method_upper}</span> `{path}`\n\n'

    if summary:
        md += f"{summary}\n\n"

    if description and description != summary:
        md += f"{description}\n\n"

    # Параметры
    parameters = operation.get("parameters", [])
    if parameters:
        md += "#### Параметры\n\n"
        for param in parameters:
            param_name = param.get("name", "")
            param_in = param.get("in", "")
            required = " (обязательно)" if param.get("required", False) else ""
            param_desc = _brand_display_text(param.get("description", ""))
            param_schema = param.get("schema", {})

            # Разворачиваем схему параметра
            if openapi_schema and param_schema:
                resolved_schema = resolve_schema_ref(param_schema, openapi_schema)
                if "type" in resolved_schema:
                    param_type = resolved_schema["type"]
                    md += f"- `{param_name}` ({param_in}, {param_type}){required}: {param_desc}\n"
                else:
                    md += f"- `{param_name}` ({param_in}){required}: {param_desc}\n"
            else:
                md += f"- `{param_name}` ({param_in}){required}: {param_desc}\n"
        md += "\n"

    # Request Body
    request_body = operation.get("requestBody", {})
    if request_body:
        md += f"#### {loc['request']}\n\n"
        content = request_body.get("content", {})
        if content:
            for content_type, schema_info in content.items():
                md += f"**Content-Type:** `{content_type}`\n\n"
                schema_obj = schema_info.get("schema", {})
                if schema_obj and openapi_schema:
                    resolved_schema = resolve_schema_ref(schema_obj, openapi_schema)

                    # Если есть properties, показываем их
                    if "properties" in resolved_schema:
                        required_fields = resolved_schema.get("required", [])
                        md += "```json\n"
                        md += "{\n"
                        for prop_name, prop_schema in resolved_schema["properties"].items():
                            prop_required = " (обязательно)" if prop_name in required_fields else ""
                            prop_type = prop_schema.get("type", "any")
                            prop_desc = _brand_display_text(prop_schema.get("description", ""))
                            md += (
                                f'  "{prop_name}": <{prop_type}>{prop_required},  // {prop_desc}\n'
                            )
                        md += "}\n"
                        md += "```\n\n"
                    else:
                        md += "```json\n"
                        md += _brand_display_text(json.dumps(resolved_schema, indent=2))
                        md += "\n```\n\n"
                elif schema_obj:
                    md += "```json\n"
                    md += _brand_display_text(json.dumps(schema_obj, indent=2))
                    md += "\n```\n\n"

    # Responses
    responses = operation.get("responses", {})
    if responses:
        md += f"#### {loc['response']}\n\n"
        for status_code, response in responses.items():
            status_desc = _brand_display_text(response.get("description", ""))
            md += f"- **{status_code}**: {status_desc}\n"
        md += "\n"

    md += "---\n\n"

    return md


def generate_service_markdown(
    service_name: str, openapi_schema: dict, intro_content: str | None = None, lang: str = "ru"
) -> str:
    """
    Генерирует Markdown страницу для сервиса.

    Args:
        service_name: Имя сервиса
        openapi_schema: OpenAPI схема
        intro_content: Ручное описание (опционально)
        lang: Код языка

    Returns:
        Полный Markdown контент
    """
    loc = LOCALIZATIONS.get(lang, LOCALIZATIONS["en"])

    info = openapi_schema.get("info", {})
    title = _brand_display_text(info.get("title", f"{service_name.title()} {loc['api_title']}"))
    description = _brand_display_text(info.get("description", ""))

    # YAML frontmatter
    md = f"---\ntitle: {json.dumps(title, ensure_ascii=False)}\n---\n\n"

    # Ручное intro если есть
    if intro_content:
        md += f"{_brand_display_text(intro_content)}\n\n"

    # Описание из OpenAPI
    if description:
        md += f"{description}\n\n"

    # Интерактивный Swagger UI
    paths = openapi_schema.get("paths", {})
    if paths:
        md += f"## {loc['interactive']}\n\n"
        md += generate_swagger_ui_embed(openapi_schema, service_name)
        md += "\n\n"

    # Список эндпоинтов
    md += f"## {loc['endpoints']}\n\n"

    if not paths:
        md += f"{loc['no_endpoints']}\n\n"
    else:
        for path, methods in sorted(paths.items()):
            for method, operation in sorted(methods.items()):
                md += generate_endpoint_markdown(path, method, operation, lang, openapi_schema)

    return md


def main() -> None:
    """Генерирует Markdown для всех сервисов."""
    root = Path(__file__).resolve().parents[1]
    openapi_dir = root / "docs" / "openapi"
    root / "docs" / "api"

    if not openapi_dir.exists():
        logger.warning(f"Директория {openapi_dir} не существует")
        return

    for lang in ["ru", "en"]:
        logger.info(f"Генерация Markdown для языка: {lang}")
        build_dir = root / "build" / f"documentation-{lang}" / "api"
        build_dir.mkdir(parents=True, exist_ok=True)

        # Генерируем индексную страницу
        index_md = f"""---
title: {json.dumps("API" if lang == "en" else "API", ensure_ascii=False)}
---

"""

        if lang == "ru":
            index_md += "Публичные API платформы Humanitec.\n\n"
        else:
            index_md += "Public APIs for Humanitec platform.\n\n"

        index_md += "## Сервисы\n\n" if lang == "ru" else "## Services\n\n"
        service_cards: list[str] = []

        for openapi_file in sorted(openapi_dir.glob("*.json")):
            service_name = openapi_file.stem

            # Пропускаем пустые схемы
            schema_text = openapi_file.read_text(encoding="utf-8")
            schema = json.loads(schema_text)

            if not schema.get("paths"):
                logger.info(f"Пропуск {service_name}: нет публичных путей")
                continue

            logger.info(f"Генерация страницы для {service_name} ({lang})")

            # Чтение ручного intro
            intro = read_intro(service_name, lang)

            # Генерация Markdown
            markdown = generate_service_markdown(service_name, schema, intro, lang)

            # Сохранение
            output_file = build_dir / service_name / "index.md"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(markdown, encoding="utf-8")

            # Добавляем в индекс
            service_title = _brand_display_text(schema.get("info", {}).get("title", service_name.title()))
            service_description = _brand_display_text(" ".join(schema.get("info", {}).get("description", "").split()))
            if not service_description:
                service_description = (
                    "Автосгенерированная справка по публичным эндпоинтам сервиса."
                    if lang == "ru"
                    else "Generated reference for public service endpoints."
                )
            service_cards.append(
                '<a class="docs-card" href="{href}/">'
                '<span class="docs-card-kicker">OpenAPI</span>'
                "<h2>{title}</h2>"
                "<p>{description}</p>"
                "</a>".format(
                    href=html.escape(service_name),
                    title=html.escape(service_title),
                    description=html.escape(service_description[:220]),
                )
            )

        if service_cards:
            index_md += '<div class="docs-card-grid docs-card-grid-compact">\n'
            index_md += "\n".join(service_cards)
            index_md += "\n</div>\n"

        # Сохранение индекса
        index_file = build_dir / "index.md"
        index_file.write_text(index_md, encoding="utf-8")
        logger.info(f"Индекс сохранён: {index_file}")

    logger.info("Генерация Markdown завершена")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()

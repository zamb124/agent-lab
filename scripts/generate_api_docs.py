"""
Генератор API документации из FastAPI OpenAPI схемы.

Запуск локально:
    python scripts/generate_api_docs.py --url http://localhost:8001

Запуск в Docker:
    docker-compose run --rm docs-generator

Переменные окружения:
    AGENTS_SERVICE_URL - URL сервиса agents (по умолчанию http://agents:8001)
    DOCS_OUTPUT_DIR - директория для записи (по умолчанию /app/docs/api)
"""

import argparse
import os
import sys
import time
import httpx
from pathlib import Path


DEFAULT_SERVICE_URL = os.getenv("AGENTS_SERVICE_URL", "http://localhost:8001")
DEFAULT_OUTPUT_DIR = os.getenv("DOCS_OUTPUT_DIR", str(Path(__file__).parent.parent / "docs" / "api"))


def get_openapi_schema(service_url: str, max_retries: int = 10, retry_delay: int = 3) -> dict:
    """Получает OpenAPI схему через HTTP запрос к сервису"""
    openapi_url = f"{service_url.rstrip('/')}/openapi.json"
    
    for attempt in range(max_retries):
        try:
            print(f"Попытка {attempt + 1}/{max_retries}: получение схемы из {openapi_url}")
            response = httpx.get(openapi_url, timeout=30.0)
            response.raise_for_status()
            print("OpenAPI схема получена успешно")
            return response.json()
        except httpx.ConnectError:
            if attempt < max_retries - 1:
                print(f"Сервис недоступен, ждем {retry_delay} сек...")
                time.sleep(retry_delay)
            else:
                raise RuntimeError(f"Не удалось подключиться к {openapi_url} после {max_retries} попыток")
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Ошибка HTTP {e.response.status_code}: {e.response.text}")


def get_method_badge(method: str) -> str:
    """Возвращает badge для HTTP метода"""
    return f'<span class="http-method {method.lower()}">{method.upper()}</span>'


def format_schema_type(schema: dict) -> str:
    """Форматирует тип из JSON Schema"""
    if not schema:
        return "any"
    
    if "$ref" in schema:
        ref = schema["$ref"].split("/")[-1]
        return f"`{ref}`"
    
    schema_type = schema.get("type", "any")
    
    if schema_type == "array":
        items = schema.get("items", {})
        item_type = format_schema_type(items)
        return f"array[{item_type}]"
    
    if schema_type == "object":
        return "object"
    
    return schema_type


def generate_endpoint_doc(path: str, method: str, operation: dict, schemas: dict) -> str:
    """Генерирует документацию для одного endpoint"""
    lines = []
    
    summary = operation.get("summary", "")
    description = operation.get("description", "")
    
    lines.append(f"### {get_method_badge(method)} `{path}`")
    lines.append("")
    
    if summary:
        lines.append(f"**{summary}**")
        lines.append("")
    
    if description:
        lines.append(description)
        lines.append("")
    
    parameters = operation.get("parameters", [])
    path_params = [p for p in parameters if p.get("in") == "path"]
    query_params = [p for p in parameters if p.get("in") == "query"]
    
    if path_params:
        lines.append("#### Параметры пути")
        lines.append("")
        lines.append("| Параметр | Тип | Описание |")
        lines.append("|----------|-----|----------|")
        for param in path_params:
            param_type = format_schema_type(param.get("schema", {}))
            lines.append(f"| `{param['name']}` | {param_type} | {param.get('description', '')} |")
        lines.append("")
    
    if query_params:
        lines.append("#### Query параметры")
        lines.append("")
        lines.append("| Параметр | Тип | Обязательный | Описание |")
        lines.append("|----------|-----|--------------|----------|")
        for param in query_params:
            param_type = format_schema_type(param.get("schema", {}))
            required = "Да" if param.get("required", False) else "Нет"
            lines.append(f"| `{param['name']}` | {param_type} | {required} | {param.get('description', '')} |")
        lines.append("")
    
    request_body = operation.get("requestBody", {})
    if request_body:
        content = request_body.get("content", {})
        json_content = content.get("application/json", {})
        schema = json_content.get("schema", {})
        
        if schema:
            lines.append("#### Тело запроса")
            lines.append("")
            
            if "$ref" in schema:
                ref_name = schema["$ref"].split("/")[-1]
                ref_schema = schemas.get(ref_name, {})
                properties = ref_schema.get("properties", {})
                required_fields = ref_schema.get("required", [])
                
                if properties:
                    lines.append("| Поле | Тип | Обязательное | Описание |")
                    lines.append("|------|-----|--------------|----------|")
                    for prop_name, prop_schema in properties.items():
                        prop_type = format_schema_type(prop_schema)
                        required = "Да" if prop_name in required_fields else "Нет"
                        desc = prop_schema.get("description", prop_schema.get("title", ""))
                        lines.append(f"| `{prop_name}` | {prop_type} | {required} | {desc} |")
                    lines.append("")
    
    responses = operation.get("responses", {})
    if responses:
        lines.append("#### Ответы")
        lines.append("")
        lines.append("| Код | Описание |")
        lines.append("|-----|----------|")
        for code, response in responses.items():
            desc = response.get("description", "")
            lines.append(f"| `{code}` | {desc} |")
        lines.append("")
    
    lines.append("---")
    lines.append("")
    
    return "\n".join(lines)


def generate_tag_doc(tag: str, tag_info: dict, endpoints: list, schemas: dict) -> str:
    """Генерирует документацию для тега (группы endpoints)"""
    lines = []
    
    title = tag_info.get("name", tag)
    description = tag_info.get("description") or f"API endpoints для {tag}"
    
    lines.append(f"# {title}")
    lines.append("")
    
    if tag_info.get("description"):
        lines.append(tag_info["description"])
        lines.append("")
    
    for path, method, operation in endpoints:
        lines.append(generate_endpoint_doc(path, method, operation, schemas))
    
    return "\n".join(lines)


def transliterate(text: str) -> str:
    """Транслитерация русского текста"""
    transliteration = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya"
    }
    result = text.lower().replace(" ", "_")
    for ru, en in transliteration.items():
        result = result.replace(ru, en)
    return result


def generate_index(tags: list[dict]) -> str:
    """Генерирует index.md для API документации"""
    lines = [
        "# API документация",
        "",
        "REST API для интеграции с платформой Agent Lab.",
        "",
        "## Базовый URL",
        "",
        "```",
        "https://your-domain.com/agents/api/v1",
        "```",
        "",
        "## Разделы API",
        "",
    ]
    
    for tag in tags:
        name = tag.get("name", "")
        description = tag.get("description", "")
        filename = transliterate(name)
        lines.append(f"- [{name}]({filename}.md) — {description}")
    
    lines.append("")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Генератор API документации из OpenAPI")
    parser.add_argument(
        "--url", 
        default=DEFAULT_SERVICE_URL,
        help=f"URL сервиса agents (по умолчанию: {DEFAULT_SERVICE_URL})"
    )
    parser.add_argument(
        "--output", 
        default=DEFAULT_OUTPUT_DIR,
        help=f"Директория для записи (по умолчанию: {DEFAULT_OUTPUT_DIR})"
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=10,
        help="Количество попыток подключения (по умолчанию: 10)"
    )
    args = parser.parse_args()
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Генерация API документации...")
    print(f"  Сервис: {args.url}")
    print(f"  Выход: {output_dir}")
    
    schema = get_openapi_schema(args.url, max_retries=args.retries)
    
    paths = schema.get("paths", {})
    tags_info = {t["name"]: t for t in schema.get("tags", [])}
    schemas = schema.get("components", {}).get("schemas", {})
    
    endpoints_by_tag: dict[str, list] = {}
    
    for path, methods in paths.items():
        for method, operation in methods.items():
            if method in ("get", "post", "put", "patch", "delete"):
                op_tags = operation.get("tags", ["Other"])
                for tag in op_tags:
                    if tag not in endpoints_by_tag:
                        endpoints_by_tag[tag] = []
                    endpoints_by_tag[tag].append((path, method, operation))
    
    generated_tags = []
    for tag, endpoints in endpoints_by_tag.items():
        if not endpoints:
            continue
            
        tag_info = tags_info.get(tag, {"name": tag, "description": ""})
        content = generate_tag_doc(tag, tag_info, endpoints, schemas)
        
        filename = transliterate(tag)
        filepath = output_dir / f"{filename}.md"
        filepath.write_text(content, encoding="utf-8")
        print(f"  Создан: {filepath}")
        
        generated_tags.append(tag_info)
    
    index_content = generate_index(generated_tags)
    index_path = output_dir / "index.md"
    index_path.write_text(index_content, encoding="utf-8")
    print(f"  Создан: {index_path}")
    
    print(f"\nГотово! Сгенерировано {len(generated_tags) + 1} файлов")


if __name__ == "__main__":
    main()

# Как определяется схема для MCP_TOOL

## Обзор процесса

Схема для MCP_TOOL определяется в несколько этапов:

1. **Получение от MCP сервера** - через JSON-RPC запрос `tools/list`
2. **Синхронизация и сохранение** - преобразование и сохранение в `ToolReference`
3. **Преобразование в Pydantic** - при создании инструмента
4. **Использование в StructuredTool** - передача в `args_schema`

---

## Этап 1: Получение схемы от MCP сервера

### JSON-RPC запрос

MCP клиент отправляет JSON-RPC запрос к серверу:

```python
# app/core/mcp_client.py
request_data = {
    "jsonrpc": "2.0",
    "id": request_id,
    "method": "tools/list"
}

response = await client.post(url, json=request_data)
```

### Формат ответа от MCP сервера

MCP сервер возвращает список тулов в формате:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "join_channel",
        "title": "Join Channel",
        "description": "Join a specific channel to communicate with Figma",
        "inputSchema": {
          "type": "object",
          "$schema": "http://json-schema.org/draft-07/schema#",
          "properties": {
            "channel": {
              "type": "string",
              "default": "",
              "description": "The name of the channel to join"
            }
          },
          "required": [],
          "additionalProperties": false
        }
      }
    ]
  }
}
```

**Ключевое поле**: `inputSchema` - это JSON Schema, описывающая параметры тула.

---

## Этап 2: Синхронизация и сохранение

### Процесс синхронизации

При синхронизации MCP сервера (`sync_mcp_server_tools`):

```python
# app/core/mcp_sync.py

# 1. Получаем список тулов от MCP сервера
tools_data = await mcp_client.list_tools()

# 2. Для каждого тула извлекаем inputSchema
for mcp_tool in tools_data:
    input_schema = mcp_tool.get("inputSchema", {})

    # 3. Преобразуем JSON Schema в формат параметров
    params = _json_schema_to_params_format(input_schema)

    # 4. Сохраняем оригинальный input_schema для tool_factory
    params["input_schema"] = input_schema

    # 5. Создаем ToolReference
    tool_ref = ToolReference(
        tool_id=f"mcp:{server_id}:{tool_name}",
        code_mode=CodeMode.MCP_TOOL,
        params=params,  # Содержит и преобразованные параметры, и input_schema
        ...
    )
```

### Преобразование JSON Schema в формат параметров

Функция `_json_schema_to_params_format` преобразует JSON Schema:

**Входной формат (JSON Schema)**:
```json
{
  "type": "object",
  "properties": {
    "channel": {
      "type": "string",
      "default": "",
      "description": "The name of the channel to join"
    }
  },
  "required": []
}
```

**Выходной формат (params)**:
```json
{
  "channel": {
    "type": "typing.Optional[<class 'str'>]",
    "required": false,
    "description": "The name of the channel to join"
  },
  "input_schema": {
    "type": "object",
    "properties": {...},
    "required": []
  }
}
```

### Логика преобразования типов

```python
# Маппинг типов JSON Schema → Python типы
type_mapping = {
    "string": "<class 'str'>",
    "integer": "<class 'int'>",
    "number": "<class 'float'>",
    "boolean": "<class 'bool'>",
    "array": "typing.List",
    "object": "typing.Dict[str, typing.Any]",
}

# Обработка Optional
if not is_required:
    python_type = f"typing.Optional[{python_type}]"

# Обработка массивов с items
if param_type == "array" and "items" in param_schema:
    items_type = param_schema["items"]["type"]
    python_type = f"typing.List[{items_python_type}]"
```

---

## Этап 3: Преобразование в Pydantic модель

### При создании инструмента

Когда агент запрашивает MCP тул, `ToolFactory` создает его:

```python
# app/core/tool_factory.py

async def _create_mcp_tool(self, ref: ToolReference):
    # 1. Извлекаем input_schema из params
    input_schema = ref.params.get("input_schema")

    # 2. Если input_schema отсутствует, восстанавливаем из преобразованных параметров
    if not input_schema:
        params_without_schema = {
            k: v for k, v in ref.params.items()
            if k != "input_schema" and isinstance(v, dict) and "type" in v
        }
        input_schema = self._params_to_json_schema(params_without_schema)

    # 3. Преобразуем JSON Schema в Pydantic модель
    args_schema = self._json_schema_to_pydantic(input_schema, tool_name)

    # 4. Создаем динамическую функцию
    async def dynamic_mcp_func(**kwargs):
        result = await mcp_client.call_tool(tool_name, kwargs)
        return format_mcp_result(result.get("content", []))

    # 5. Оборачиваем в @tool декоратор с args_schema
    mcp_tool = tool(
        description=ref.description,
        args_schema=args_schema,  # Pydantic модель
        infer_schema=False,  # Отключаем auto-infer
        ...
    )(dynamic_mcp_func)
```

### Преобразование JSON Schema → Pydantic

Функция `_json_schema_to_pydantic`:

```python
def _json_schema_to_pydantic(self, schema: Dict[str, Any], model_name: str):
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    fields = {}
    for field_name, field_spec in properties.items():
        # 1. Определяем Python тип
        field_type = self._json_type_to_python(field_spec.get("type", "string"))

        # 2. Обрабатываем default
        if "default" in field_spec:
            default = field_spec["default"]
            is_required = False  # Поле с default всегда опциональное
        elif field_name in required:
            default = ...  # Обязательное поле
        else:
            default = None  # Опциональное поле
            field_type = typing.Optional[field_type]

        # 3. Создаем поле Pydantic
        fields[field_name] = (
            field_type,
            PydanticField(default=default, description=field_spec.get("description", ""))
        )

    # 4. Создаем Pydantic модель
    return create_model(f"{model_name}Input", **fields)
```

### Маппинг типов JSON Schema → Python

```python
def _json_type_to_python(self, json_type: str) -> type:
    mapping = {
        "string": str,
        "number": float,
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    return mapping.get(json_type, str)
```

---

## Этап 4: Использование в StructuredTool

### Передача args_schema

Pydantic модель передается в `@tool` декоратор:

```python
mcp_tool = tool(
    description=ref.description,
    args_schema=args_schema,  # Pydantic модель с полями
    infer_schema=False,  # Важно: отключаем автоматическое определение
    ...
)(dynamic_mcp_func)
```

### Структура Pydantic модели

Пример созданной модели:

```python
# Для тула join_channel с параметром channel (optional, default="")
JoinChannelInput = create_model(
    "JoinChannelInput",
    channel=(typing.Optional[str], Field(default="", description="The name of the channel to join"))
)
```

### Использование LLM

Когда LLM вызывает инструмент:

1. **LLM видит схему** через `args_schema.model_fields`
2. **Валидация параметров** происходит через Pydantic
3. **Вызов MCP сервера** с валидированными параметрами

---

## Полный поток данных

```
MCP Сервер
    ↓
    JSON-RPC: tools/list
    ↓
    inputSchema (JSON Schema)
    ↓
mcp_client.list_tools()
    ↓
sync_mcp_server_tools()
    ↓
_json_schema_to_params_format()
    ↓
ToolReference.params = {
    "channel": {"type": "...", "required": false, ...},
    "input_schema": {...}  # Оригинальная JSON Schema
}
    ↓
tool_factory._create_mcp_tool()
    ↓
_json_schema_to_pydantic()
    ↓
Pydantic модель (args_schema)
    ↓
@tool(args_schema=args_schema)
    ↓
StructuredTool
    ↓
LLM видит схему и использует инструмент
```

---

## Особенности обработки

### 1. Поля с default

Если в JSON Schema есть `default`, поле становится опциональным:

```python
# JSON Schema
{
  "channel": {
    "type": "string",
    "default": ""
  }
}

# Pydantic
channel: Optional[str] = Field(default="")
```

### 2. Обязательные поля

Если поле в `required`, оно обязательное:

```python
# JSON Schema
{
  "required": ["file_path"],
  "properties": {
    "file_path": {"type": "string"}
  }
}

# Pydantic
file_path: str = Field(...)  # Обязательное
```

### 3. Опциональные поля

Если поле не в `required` и нет `default`:

```python
# Pydantic
channel: Optional[str] = Field(default=None)
```

### 4. Восстановление схемы

Если `input_schema` отсутствует в `params`, система восстанавливает его из преобразованных параметров через `_params_to_json_schema()`.

---

## Примеры

### Пример 1: Простой параметр

**MCP сервер возвращает**:
```json
{
  "name": "get_weather",
  "inputSchema": {
    "properties": {
      "city": {"type": "string", "description": "City name"}
    },
    "required": ["city"]
  }
}
```

**В ToolReference.params**:
```json
{
  "city": {
    "type": "<class 'str'>",
    "required": true,
    "description": "City name"
  },
  "input_schema": {...}
}
```

**Pydantic модель**:
```python
GetWeatherInput = create_model(
    "GetWeatherInput",
    city=(str, Field(..., description="City name"))
)
```

### Пример 2: Опциональный параметр с default

**MCP сервер возвращает**:
```json
{
  "name": "join_channel",
  "inputSchema": {
    "properties": {
      "channel": {
        "type": "string",
        "default": "",
        "description": "Channel name"
      }
    },
    "required": []
  }
}
```

**Pydantic модель**:
```python
JoinChannelInput = create_model(
    "JoinChannelInput",
    channel=(Optional[str], Field(default="", description="Channel name"))
)
```

---

## Отладка

### Логирование

Система логирует все этапы:

```python
# При синхронизации
logger.info(f"📋 MCP тул {tool_name}: properties={list(properties.keys())}")

# При создании инструмента
logger.info(f"📋 MCP tool {tool_name} input_schema: {json.dumps(input_schema, indent=2)}")
logger.info(f"📋 MCP tool {tool_name} args_schema поля: {json.dumps(fields_info, indent=2)}")
logger.info(f"✅ MCP tool {tool_name} создан, финальная схема: {final_fields}")
```

### Проверка схемы в БД

```python
# Получить ToolReference
tool_ref = await tool_repo.get("mcp:figma_designer:join_channel")

# Проверить params
print(tool_ref.params["input_schema"])  # Оригинальная JSON Schema
print(tool_ref.params["channel"])  # Преобразованные параметры
```

---

## Проблемы и решения

### Проблема: Пустая схема

**Симптом**: LLM получает функцию без параметров

**Причина**: `input_schema` пустой или не содержит `properties`

**Решение**:
1. Проверить логи синхронизации
2. Убедиться, что MCP сервер возвращает правильный `inputSchema`
3. Проверить восстановление схемы через `_params_to_json_schema()`

### Проблема: Неправильные типы

**Симптом**: Ошибки валидации при вызове

**Причина**: Неправильное преобразование типов JSON Schema → Python

**Решение**: Проверить маппинг в `_json_type_to_python()` и обработку Optional

---

## Итоговая схема

```
MCP Сервер (JSON Schema)
    ↓
Синхронизация (преобразование в params формат)
    ↓
ToolReference.params (два формата: преобразованный + оригинальный)
    ↓
Создание инструмента (JSON Schema → Pydantic)
    ↓
StructuredTool.args_schema (Pydantic модель)
    ↓
LLM (видит схему и использует)
```



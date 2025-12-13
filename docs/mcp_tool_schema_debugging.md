# Диагностика проблемы: MCP_TOOL без параметров в LLM

## Проблема

LLM получает функцию без параметров:
```json
{
  "function": {
    "name": "join_channel",
    "arguments": "{}"
  }
}
```

## Где искать логи

### 1. Логи синхронизации MCP сервера

**Когда**: При синхронизации MCP сервера (`sync_mcp_server_tools`)

**Что искать**:
```
📋 MCP тул join_channel: properties=['channel'], required=[]
📋 MCP tool join_channel input_schema: {...}
✅ Синхронизирован MCP тул: mcp:figma_designer:join_channel
```

**Проверка**:
- `properties` не должен быть пустым
- `input_schema` должен содержать `properties` с параметрами

**Где**: Логи при вызове синхронизации MCP сервера

---

### 2. Логи создания инструмента

**Когда**: При создании MCP инструмента в `ToolFactory._create_mcp_tool()`

**Что искать**:
```
🎯 Создание MCP tool: mcp:figma_designer:join_channel
📦 Разобран MCP tool: server=figma_designer, tool=join_channel
📋 MCP tool join_channel финальный input_schema: {...}
📋 _json_schema_to_pydantic для join_channel: properties=['channel'], required=[]
📋 MCP tool join_channel args_schema создана: <class 'join_channelInput'>
📋 MCP tool join_channel args_schema поля: {"channel": {...}}
📋 MCP tool join_channel создается с args_schema: ['channel'], infer_schema=False
✅ MCP tool join_channel создан, финальная схема: ['channel']
```

**Проверка**:
- `input_schema` не должен быть пустым
- `args_schema` должна иметь `model_fields` с полями
- `args_schema поля` должен содержать параметры
- `финальная схема` не должна быть пустой

**Где**: Логи при загрузке агента или создании инструментов

---

### 3. Логи декоратора @tool

**Когда**: При применении декоратора `@tool` к MCP функции

**Что искать**:
```
🔍 @tool декоратор: передаем args_schema с полями: ['channel']
✅ @tool декоратор: langchain_decorated.args_schema имеет поля: ['channel']
🔍 @tool state_aware: оригинальная схема join_channelInput
🔍 @tool state_aware: оригинальные поля: ['channel']
🔍 Создаем схему join_channelInputWithState с полями: ['channel']
✅ Схема join_channelInputWithState создана успешно с 1 полями
✅ Финальная схема имеет поля: ['channel']
✅ Схема заменена на join_channelInputWithState
```

**Проверка**:
- `передаем args_schema с полями` не должен быть пустым
- `langchain_decorated.args_schema` должен иметь поля
- `оригинальные поля` не должны быть пустыми
- `Создаем схему ...WithState` должна содержать поля

**Где**: Логи при создании инструмента (должны быть на уровне DEBUG)

---

### 4. Логи конвертации в OpenRouter формат

**Когда**: При вызове LLM с инструментами (`_convert_tools_to_openrouter_format`)

**Что искать**:
```
🔍 Конвертация tool join_channel: args_schema тип=<class 'join_channelInputWithState'>
🔍 Tool join_channel: args_schema имеет model_fields: ['channel']
🔍 Tool join_channel: model_json_schema() вернул properties: ['channel']
📋 Tool join_channel финальные parameters.properties: ['channel']
```

**Проверка**:
- `args_schema имеет model_fields` не должен быть пустым
- `model_json_schema() вернул properties` не должен быть пустым
- `финальные parameters.properties` не должен быть пустым

**Если видите**:
```
⚠️ Tool join_channel: args_schema не имеет model_fields
⚠️ Tool join_channel: model_json_schema() вернул пустые properties!
⚠️ Tool join_channel: нет args_schema или args_schema is None
```

**Где**: Логи при вызове LLM (должны быть на уровне INFO/DEBUG)

---

### 5. Логи LLM запроса

**Когда**: При отправке запроса в OpenRouter

**Что искать**:
```
LLM запрос:
{
  "model": "...",
  "messages": [...],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "join_channel",
        "description": "...",
        "parameters": {
          "type": "object",
          "properties": {
            "channel": {
              "type": "string",
              "description": "..."
            }
          },
          "required": []
        }
      }
    }
  ]
}
```

**Проверка**:
- `tools[].function.parameters.properties` не должен быть пустым `{}`
- Должны быть все параметры из схемы

**Где**: Логи при вызове LLM (уровень INFO)

---

## Пошаговая диагностика

### Шаг 1: Проверка сохранения в БД

```python
from app.core.container import get_container

tool_repo = get_container().tool_repository
tool_ref = await tool_repo.get("mcp:figma_designer:join_channel")

# Проверяем input_schema
input_schema = tool_ref.params.get("input_schema")
print("input_schema:", json.dumps(input_schema, indent=2))

# Проверяем преобразованные параметры
params = {k: v for k, v in tool_ref.params.items() if k != "input_schema"}
print("params:", json.dumps(params, indent=2))
```

**Ожидаемый результат**:
- `input_schema` содержит JSON Schema с `properties`
- `params` содержит преобразованные параметры с ключами типа `channel`

---

### Шаг 2: Проверка создания инструмента

```python
from app.core.container import get_container

tool_factory = get_container().tool_factory
tool_ref = await tool_repo.get("mcp:figma_designer:join_channel")

tools = await tool_factory.create_tools([tool_ref])
tool = tools[0]

# Проверяем args_schema
if hasattr(tool, 'args_schema') and tool.args_schema:
    schema = tool.args_schema
    if hasattr(schema, 'model_fields'):
        print("Поля схемы:", list(schema.model_fields.keys()))

        # Проверяем model_json_schema
        json_schema = schema.model_json_schema()
        print("JSON Schema properties:", list(json_schema.get('properties', {}).keys()))
    else:
        print("❌ args_schema не имеет model_fields")
else:
    print("❌ args_schema отсутствует или None")
```

**Ожидаемый результат**:
- `Поля схемы` содержит `['channel']`
- `JSON Schema properties` содержит `['channel']`

---

### Шаг 3: Проверка конвертации в OpenRouter

При вызове LLM проверьте логи:
```
🔍 Конвертация tool join_channel: args_schema тип=...
🔍 Tool join_channel: args_schema имеет model_fields: ['channel']
📋 Tool join_channel финальные parameters.properties: ['channel']
```

**Если видите пустые properties**:
- Проверьте, что `args_schema` не None
- Проверьте, что `model_json_schema()` возвращает правильную схему
- Проверьте логи создания инструмента (Шаг 2)

---

## Типичные проблемы и решения

### Проблема 1: `input_schema` пустой в БД

**Симптом**: В логах синхронизации `properties=[]`

**Решение**:
1. Проверьте, что MCP сервер возвращает правильный `inputSchema`
2. Проверьте логи синхронизации на ошибки
3. Пересинхронизируйте MCP сервер

---

### Проблема 2: `args_schema` пустая при создании

**Симптом**: В логах `args_schema поля: {}`

**Решение**:
1. Проверьте, что `input_schema` правильно извлекается из `params`
2. Проверьте логи `_json_schema_to_pydantic` - должна быть схема с `properties`
3. Проверьте, что `input_schema` содержит `properties`

---

### Проблема 3: Схема теряется в декораторе

**Симптом**: В логах `@tool` оригинальные поля пустые

**Решение**:
1. Проверьте, что `args_schema` передается в `@tool` декоратор
2. Проверьте, что `langchain_tool` правильно обрабатывает схему
3. Проверьте, что при создании `WithState` схемы поля не теряются

---

### Проблема 4: Пустые properties в OpenRouter

**Симптом**: В логах `model_json_schema() вернул пустые properties!`

**Решение**:
1. Проверьте, что `args_schema` имеет `model_fields`
2. Проверьте, что `model_json_schema()` вызывается правильно
3. Проверьте логи создания инструмента - схема должна быть валидной

---

## Команды для проверки

### Проверка в БД
```python
# В Python консоли или скрипте
from app.core.container import get_container
import json

tool_repo = get_container().tool_repository
tool_ref = await tool_repo.get("mcp:figma_designer:join_channel")

print("input_schema:", json.dumps(tool_ref.params.get("input_schema"), indent=2))
print("params keys:", [k for k in tool_ref.params.keys() if k != "input_schema"])
```

### Проверка создания инструмента
```python
from app.core.container import get_container

tool_factory = get_container().tool_factory
tool_repo = get_container().tool_repository

tool_ref = await tool_repo.get("mcp:figma_designer:join_channel")
tools = await tool_factory.create_tools([tool_ref])

tool = tools[0]
print("tool.args_schema:", tool.args_schema)
if tool.args_schema:
    print("model_fields:", list(tool.args_schema.model_fields.keys()))
    print("model_json_schema:", tool.args_schema.model_json_schema())
```

### Проверка конвертации
```python
from app.core.llm_billing_wrapper import ChatOpenAIWithBilling

# Создайте LLM и привяжите инструменты
llm = ChatOpenAIWithBilling(...)
llm.bind_tools(tools)

# Проверьте _bound_tools
print("_bound_tools:", llm._bound_tools)
for tool in llm._bound_tools:
    print(f"{tool.name}: args_schema={tool.args_schema}")

# Проверьте конвертацию
openrouter_tools = llm._convert_tools_to_openrouter_format(llm._bound_tools)
print("openrouter_tools:", json.dumps(openrouter_tools, indent=2))
```

---

## Ключевые точки проверки

1. ✅ **Синхронизация**: `input_schema` сохраняется в БД с `properties`
2. ✅ **Создание**: `args_schema` создается с `model_fields`
3. ✅ **Декоратор**: Схема не теряется при применении `@tool`
4. ✅ **Конвертация**: `model_json_schema()` возвращает `properties`
5. ✅ **LLM запрос**: `tools[].function.parameters.properties` не пустой

Если на любом этапе схема пустая - проблема на этом этапе!



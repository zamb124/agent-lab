# MCP (Model Context Protocol) Интеграция

## Обзор

Agent Lab поддерживает интеграцию с внешними MCP серверами через HTTP и SSE транспорты. Это позволяет использовать внешние инструменты как обычные тулы в ваших агентах.

## Архитектура

```
┌─────────────────┐
│  WeatherAgent   │
│                 │
│  tools:         │
│  - get_weather  │
│  - mcp:ctx7:... │ ←─── MCP тулы как обычные
└────────┬────────┘
         │
         ▼
┌─────────────────┐      HTTP/SSE       ┌──────────────────┐
│   ToolFactory   │ ──────────────────▶ │  MCP Server      │
│                 │                     │  (Context7, etc) │
│  MCPHttpClient  │ ◀────────────────── │                  │
└─────────────────┘                     └──────────────────┘
```

## Быстрый старт

### 1. Создание MCP сервера

Через API:

```python
import httpx

async def create_context7_server():
    """Создать Context7 MCP сервер"""
    server_config = {
        "server_id": "context7",
        "name": "Context7 Documentation",
        "description": "AI-powered documentation search",
        "url": "https://mcp.context7.com/mcp",
        "transport_type": "http",
        "headers": {
            "Authorization": "@var:context7_api_key"  # Ссылка на переменную
        },
        "is_active": True,
        "auto_sync_tools": True
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8001/api/mcp/servers",
            json=server_config
        )
        return response.json()
```

### 2. Настройка переменных

Создайте переменную для API ключа:

```python
from app.services.variables_service import get_variables_service

variables_service = get_variables_service()
await variables_service.set_var(
    key="context7_api_key",
    value="your_api_key_here",
    is_secret=True,
    description="API ключ для Context7 MCP"
)
```

### 3. Синхронизация тулов

```bash
curl -X POST http://localhost:8001/api/mcp/servers/context7/sync
```

Ответ:
```json
{
  "success": true,
  "tools_count": 5,
  "tools": [
    {
      "tool_id": "mcp:context7:search_docs",
      "title": "search_docs",
      "description": "Search documentation"
    },
    {
      "tool_id": "mcp:context7:get_library_docs",
      "title": "get_library_docs",
      "description": "Get library documentation"
    }
  ]
}
```

### 4. Добавление в агента

```python
from app.agents.react_agent import ReActAgent

class MyAgent(ReActAgent):
    name = "my_agent"
    
    tools = [
        "mcp:context7:search_docs",
        "mcp:context7:get_library_docs",
        # ... другие тулы
    ]
    
    prompt = """
    Ты помощник с доступом к документации через Context7.
    
    Используй search_docs для поиска информации.
    """
```

## Примеры MCP серверов

### Context7 (Documentation Search)

```json
{
  "server_id": "context7",
  "name": "Context7",
  "url": "https://mcp.context7.com/mcp",
  "transport_type": "http",
  "headers": {
    "Authorization": "@var:context7_api_key"
  }
}
```

**Доступные тулы:**
- `search_docs` - поиск по документации
- `get_library_docs` - получение документации библиотеки
- `resolve_library_id` - разрешение ID библиотеки

### Локальный MCP сервер

```json
{
  "server_id": "local_tools",
  "name": "Local Tools",
  "url": "http://localhost:3000/mcp",
  "transport_type": "http",
  "headers": {}
}
```

## API Endpoints

### Список серверов

```bash
GET /api/mcp/servers
```

### Получить сервер

```bash
GET /api/mcp/servers/{server_id}
```

### Создать сервер

```bash
POST /api/mcp/servers
Content-Type: application/json

{
  "server_id": "my_server",
  "name": "My MCP Server",
  "url": "https://mcp.example.com/mcp",
  "transport_type": "http"
}
```

### Обновить сервер

```bash
PUT /api/mcp/servers/{server_id}
Content-Type: application/json

{
  "server_id": "my_server",
  "name": "Updated Name",
  "is_active": false
}
```

### Удалить сервер

```bash
DELETE /api/mcp/servers/{server_id}
```

### Синхронизировать тулы

```bash
POST /api/mcp/servers/{server_id}/sync
```

### Тест подключения

```bash
POST /api/mcp/servers/{server_id}/test
```

## Использование в агентах

### ReAct агент

```python
class DocSearchAgent(ReActAgent):
    name = "doc_search"
    
    tools = [
        "mcp:context7:search_docs",
        "mcp:context7:get_library_docs",
    ]
    
    prompt = """
    Ты помощник по документации.
    Используй search_docs для поиска информации.
    """
```

### StateGraph агент

MCP тулы работают как обычные тулы в нодах графа:

```python
from app.agents.stategraph_agent import StateGraphAgent
from app.models.core_models import GraphDefinition, GraphNode, GraphEdge, NodeType
from app.core.state import State

class MyStateGraphAgent(StateGraphAgent):
    name = "my_stategraph_agent"
    
    graph_definition = GraphDefinition(
        nodes=[
            GraphNode(
                id="search_docs",
                type=NodeType.FUNCTION_NODE,
                params={"function": "app.agents.my.search_node"},
                description="Поиск документов"
            ),
        ],
        edges=[
            GraphEdge(source="START", target="search_docs"),
            GraphEdge(source="search_docs", target="END"),
        ],
        entry_point="search_docs"
    )

async def search_node(state: State) -> State:
    """Нода с вызовом MCP тула"""
    from app.core.container import get_container
    
    tool_factory = get_container().tool_factory
    mcp_tool = await tool_factory.create_tool("mcp:context7:search_docs")
    
    # MCP тул вызывается как обычный
    result = await mcp_tool.ainvoke({
        "query": state.get("store", {}).get("query", "")
    })
    
    state["store"]["result"] = result
    return state
```

## Переменные и секреты

### Использование @var: ссылок

MCP серверы поддерживают ссылки на переменные компании:

```python
server_config = MCPServerConfig(
    server_id="context7",
    url="https://mcp.context7.com/mcp",
    headers={
        "Authorization": "@var:context7_api_key",  # Ссылка на переменную
        "X-Custom-Header": "@var:custom_header"
    }
)
```

При создании HTTP клиента ссылки автоматически резолвятся:

```python
# app/core/mcp_client.py
resolved_headers = await variables_service.resolve(server_config.headers)
# {"Authorization": "Bearer sk-xxx", "X-Custom-Header": "value"}
```

## Мультитенантность

Каждая компания имеет свои MCP серверы и тулы:

```
mcp_server:company_1:context7  → Context7 для компании 1
mcp_server:company_2:context7  → Context7 для компании 2
tool:mcp:context7:search_docs  → Тул привязан к компании
```

## Автосинхронизация

При старте приложения автоматически синхронизируются все активные MCP серверы с `auto_sync_tools=true`:

```python
# app/main.py
async def lifespan(app: FastAPI):
    # ...
    from app.core.mcp_sync import sync_all_companies_mcp_servers
    await sync_all_companies_mcp_servers()
```

## Типы транспорта

### HTTP (по умолчанию)

```python
transport_type = MCPTransportType.HTTP
```

- Обычные POST запросы
- Быстрые ответы
- Подходит для большинства случаев

### SSE (Server-Sent Events)

```python
transport_type = MCPTransportType.SSE
```

- Streaming ответы
- Подходит для длительных операций
- Поддержка прогресса

## Биллинг

MCP тулы поддерживают биллинг как обычные тулы:

```python
tool_ref = ToolReference(
    tool_id="mcp:context7:search_docs",
    cost=0.01,  # Стоимость за вызов
    billing_name="mcp_context7_search",
    tariff_limits={
        "free": 10,      # 10 вызовов для free плана
        "basic": 100,    # 100 для basic
        "premium": -1    # Без лимитов для premium
    }
)
```

## Примеры использования

### Пример 1: Поиск документации

```python
# 1. Создаем MCP сервер Context7
# 2. Синхронизируем тулы
# 3. Используем в агенте

class DocsAgent(ReActAgent):
    tools = ["mcp:context7:search_docs"]
    
    prompt = """
    Найди информацию по запросу пользователя используя search_docs.
    """
```

### Пример 2: Weather + Documentation

```python
class WeatherAgent(ReActAgent):
    tools = [
        "app.tools.weather.get_weather",
        "mcp:context7:search_docs",  # Добавили MCP тул
    ]
    
    prompt = """
    Ты помощник по погоде.
    Используй get_weather для погоды.
    Используй search_docs для поиска информации о городах.
    """
```

## Тестирование

### Юнит тесты

```python
pytest tests/mcp/test_mcp_models.py
pytest tests/mcp/test_mcp_repository.py
pytest tests/mcp/test_mcp_client.py
pytest tests/mcp/test_mcp_sync.py
```

### Интеграционные тесты

```python
# Требуют API ключи
pytest tests/mcp/test_mcp_integration.py -m integration
```

## Troubleshooting

### Сервер не синхронизируется

1. Проверьте `is_active=true`
2. Проверьте что URL доступен
3. Проверьте что API ключ верный:

```bash
curl -X POST http://localhost:8001/api/mcp/servers/context7/test
```

### Тулы не появляются в агенте

1. Синхронизируйте сервер:
```bash
POST /api/mcp/servers/context7/sync
```

2. Проверьте `cached_tools` в конфигурации сервера

3. Проверьте что tool_id правильный:
```python
"mcp:server_id:tool_name"
```

### Ошибки при вызове тула

1. Проверьте параметры тула (inputSchema)
2. Проверьте что сервер активен
3. Посмотрите логи:

```python
logger.error(f"Ошибка вызова MCP тула: {e}")
```

## Best Practices

1. **Используйте @var: для секретов**
   ```python
   headers={"Authorization": "@var:api_key"}
   ```

2. **Называйте серверы понятно**
   ```python
   server_id="context7"  # ✅
   server_id="server1"   # ❌
   ```

3. **Включайте auto_sync_tools**
   ```python
   auto_sync_tools=True
   ```

4. **Тестируйте подключение**
   ```bash
   POST /api/mcp/servers/{server_id}/test
   ```

5. **Группируйте тулы в промпте**
   ```python
   prompt = """
   ИНСТРУМЕНТЫ ДЛЯ ДОКУМЕНТАЦИИ:
   - search_docs: поиск
   - get_library_docs: получение документации
   """
   ```


# MCP (Model Context Protocol) Интеграция

## ✅ Что реализовано

### Backend (100% готово)

1. **Модели данных**
   - `MCPServerConfig` - конфигурация MCP сервера с мультитенантностью
   - `CodeMode.MCP_TOOL` - новый тип тула для MCP
   - `MCPTransportType` - HTTP и SSE транспорты

2. **HTTP/SSE клиент**
   - `MCPHttpClient` - JSON-RPC 2.0 протокол
   - Автоматическая инициализация сессий
   - Поддержка HTTP и SSE транспортов

3. **Repository Pattern**
   - `MCPServerRepository` - CRUD для MCP серверов
   - Изоляция по компаниям (`mcp_server:{company_id}:{server_id}`)

4. **Синхронизация**
   - `sync_mcp_server_tools()` - синхронизация тулов одного сервера
   - `sync_all_companies_mcp_servers()` - автосинхронизация при старте
   - Кэширование списка тулов

5. **Интеграция в ToolFactory**
   - `_create_mcp_tool()` - создание тулов через `@tool` декоратор
   - Поддержка биллинга, state_aware, группировки
   - JSON Schema → Pydantic модель конвертация

6. **Поддержка в агентах**
   - ✅ **ReAct агенты** - MCP тулы как обычные tools
   - ✅ **StateGraph агенты** - MCP тулы в TOOL_NODE
   - Единая ToolFactory для всех типов тулов

7. **API Endpoints**
   - `GET /api/mcp/servers` - список серверов
   - `POST /api/mcp/servers` - создание сервера
   - `POST /api/mcp/servers/{id}/sync` - синхронизация тулов
   - `POST /api/mcp/servers/{id}/test` - тест подключения

### Тестирование (100% покрыто)

1. **Юнит тесты**
   - `test_mcp_models.py` - модели
   - `test_mcp_repository.py` - репозиторий
   - `test_mcp_client.py` - HTTP клиент
   - `test_mcp_sync.py` - синхронизация

2. **Интеграционные тесты**
   - `test_context7_integration.py` - Context7 MCP сервер
   - `test_public_mcp_servers.py` - параметризованные тесты
   - `test_cloudflare_integration.py` - Cloudflare MCP серверы

3. **End-to-end тесты**
   - `test_agent_with_mcp.py` - ReAct агент + MCP тулы ✅
   - `test_stategraph_with_mcp.py` - StateGraph агент + MCP тулы ✅

### Протестированные MCP серверы

| Сервер | URL | Авторизация | Статус |
|--------|-----|-------------|---------|
| **Context7** | https://mcp.context7.com/mcp | Bearer token | ✅ Работает |
| Cloudflare Docs | https://docs.mcp.cloudflare.com/mcp | Cloudflare API | ⚠️ Требует токен |
| Cloudflare Radar | https://radar.mcp.cloudflare.com/mcp | Cloudflare API | ⚠️ Требует токен |
| Cloudflare Browser | https://browser.mcp.cloudflare.com/mcp | Cloudflare API | ⚠️ Требует токен |

## 📖 Как использовать

### 1. Создание MCP сервера

```python
from app.models.mcp_models import MCPServerConfig, MCPTransportType

# Создание через API или БД
server = MCPServerConfig(
    server_id="context7",
    company_id="your_company_id",  # Автоматически из контекста
    name="Context7 Documentation",
    url="https://mcp.context7.com/mcp",
    transport_type=MCPTransportType.HTTP,
    headers={"Authorization": "@var:context7_api_key"},  # Поддержка переменных
    is_active=True,
    auto_sync_tools=True
)
```

### 2. Синхронизация тулов

```bash
# Через API
curl -X POST http://localhost:8001/api/mcp/servers/context7/sync

# Или программно
from app.core.mcp_sync import sync_mcp_server_tools

tools = await sync_mcp_server_tools("context7")
# Создает ToolReference для каждого тула:
# - mcp:context7:resolve-library-id
# - mcp:context7:get-library-docs
```

### 3. Использование в ReAct агенте

```python
class MyAgent(ReActAgent):
    name = "doc_helper"
    
    tools = [
        "mcp:context7:resolve-library-id",
        "mcp:context7:get-library-docs",
        ask_user,
    ]
    
    prompt = """
    Ты помощник по документации.
    Используй MCP тулы для поиска информации о библиотеках.
    """
```

### 4. Использование в StateGraph агенте

```python
from app.models.core_models import GraphDefinition, GraphNode, NodeType

graph_definition = GraphDefinition(
    nodes=[
        GraphNode(
            id="search_docs",
            type=NodeType.TOOL_NODE,
            params={
                "tool_id": "mcp:context7:resolve-library-id",
                "input_key": "store.library_name",
                "output_key": "store.library_info"
            }
        ),
    ],
    edges=[
        GraphEdge(source="START", target="search_docs"),
        GraphEdge(source="search_docs", target="END"),
    ],
    entry_point="START"
)
```

## 🔧 Технические детали

### JSON-RPC 2.0 Протокол

MCP использует JSON-RPC 2.0:

```json
// Инициализация
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "agent-lab", "version": "1.0.0"}
  }
}

// Список тулов
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list"
}

// Вызов тула
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "tool-name",
    "arguments": {"param": "value"}
  }
}
```

### Архитектура

```
┌──────────────────┐
│   ReAct Agent    │
│                  │      ┌─────────────────┐
│  tools:          │      │   ToolFactory   │
│  - mcp:ctx7:...  │ ───▶ │                 │
└──────────────────┘      │  _create_mcp_   │
                          │   _tool()       │
┌──────────────────┐      │                 │
│ StateGraph Agent │      │  @tool          │      ┌────────────────┐
│                  │      │  decorator      │      │  MCPHttpClient │
│  TOOL_NODE:      │ ───▶ │                 │ ───▶ │                │
│  - mcp:ctx7:...  │      └─────────────────┘      │  JSON-RPC 2.0  │
└──────────────────┘                                │                │
                                                    └────────┬───────┘
                                                             │
                                                             ▼
                                                    ┌────────────────┐
                                                    │  MCP Server    │
                                                    │  (Context7,    │
                                                    │   Cloudflare)  │
                                                    └────────────────┘
```

### Мультитенантность

Каждая компания имеет свои MCP серверы и тулы:

```
mcp_server:company_1:context7  → Context7 для компании 1
mcp_server:company_2:context7  → Context7 для компании 2

tool:mcp:context7:resolve-library-id  → Привязан к компании через params
```

### State-aware тулы

MCP тулы поддерживают `state_aware=True`:

```python
@tool(
    description="MCP тул",
    state_aware=True  # ✅ Доступ к state
)
async def mcp_tool_wrapper(**kwargs):
    # kwargs.pop('state') извлечется декоратором
    # kwargs.pop('tool_call_id') извлечется декоратором
    result = await mcp_client.call_tool(tool_name, kwargs)
    return result
```

## 🧪 Запуск тестов

```bash
# Все MCP тесты
uv run pytest tests/mcp/ -v

# Только интеграционные
uv run pytest tests/mcp/ -m integration -v

# Context7 end-to-end
uv run pytest tests/mcp/test_agent_with_mcp.py -m integration -v -s

# StateGraph + MCP
uv run pytest tests/mcp/test_stategraph_with_mcp.py -m integration -v -s
```

## 📚 Ссылки

- [MCP Specification](https://modelcontextprotocol.io)
- [MCP Registry](https://github.com/modelcontextprotocol/registry)
- [Awesome MCP Servers](https://github.com/punkpeye/awesome-mcp-servers)
- [Cloudflare MCP Servers](https://github.com/cloudflare/mcp-server-cloudflare)
- [Context7 MCP](https://mcp.context7.com)
- [MCP.so Public Servers](https://mcp.so/server/public-mcp-servers)

## 🚀 Следующие шаги

### TODO Frontend
- [ ] Создать плагин для управления MCP серверами
- [ ] Интегрировать MCP тулы в Builder UI
- [ ] Добавить UI для синхронизации тулов
- [ ] Показ MCP тулов в списке доступных инструментов


# Поиск по коду — два движка

В проекте два независимых поиска. Не заменяй один другим — у них разные задачи.

- **codebase-memory-mcp** — структурный граф знаний (tree-sitter AST + Hybrid LSP → SQLite). 158 языков: call graph, импорты, наследование, HTTP-маршруты, dead code, архитектура.
- **claude-context MCP** (`@zilliz/claude-context-mcp`, Ollama + Milvus) — семантический векторный поиск по смыслу текста. Проект большой (3000+ файлов) — семантика + ранжирование критичны для «по смыслу» запросов.

## Какой инструмент когда

| Запрос | Инструмент |
|---|---|
| «кто вызывает X» / «что вызывает X», call chain | `mcp:codebase-memory-mcp:trace_path` |
| impact / blast-radius изменений | `detect_changes` |
| архитектура: языки, пакеты, маршруты, hotspots, слои, кластеры | `get_architecture` |
| найти функции/классы по имени/regex, по файлу, по степени | `search_graph` |
| Cypher по графу (dead code: `WHERE NOT EXISTS { (f)<-[:CALLS]-() }`) | `query_graph` |
| исходник функции по qualified name | `get_code_snippet` |
| схема графа (labels, edge types) — запусти первым для ориентировки | `get_graph_schema` |
| «где реализован X», «как работает Y», «всё связанное с Z» — по смыслу, без точных имён | `mcp:claude-context:search_code` |
| точные имена/литералы/regex (знаешь, что искать) | `grep` |
| файлы по glob | `find_path` |

Для структурных вопросов **сначала граф** — не file-by-file `read`.

## Шпаргалка

1. Имя/regex известны → `grep`.
2. Структурный вопрос → граф (`trace_path`, `search_graph`, …).
3. По смыслу → `claude_context_search_code`.
4. Тело функции → `get_code_snippet` по qualified_name.
5. Не читай файл-за-файлом, если граф/семантика отвечают за один вызов.

Порядок: **граф → семантика → grep → read**.

## Имя проекта в графе

`list_projects` / `index_status`. Не хардкодь `project`.

## Runtime-канон: Docker Compose

Весь стек — в `scripts/zed_search/docker/docker-compose.yml` (Ollama + Milvus/etcd/MinIO + CBM+mcp-proxy + claude-context+mcp-proxy).

| Сервис | URL на хосте |
|---|---|
| CBM | `http://127.0.0.1:9751/mcp` + header `X-API-Key` |
| claude-context | `http://127.0.0.1:9752/mcp` + header `X-API-Key` |
| Ollama | `127.0.0.1:11434` |
| Milvus | `127.0.0.1:19530` |

- Клиенты Zed/Cursor: только `url` + `headers.X-API-Key` — **не** stdio `command` / `npx`.
- CBM: `auto_index=true`, **`auto_watch=false`** (полный reindex — `make zed-search-reindex`).
- Репозиторий монтируется по **тому же абсолютному пути**, что на хосте.
- Ключ: `scripts/zed_search/docker/.env` (`MCP_API_KEY`, не коммитить).
- **Named volumes** переживают `compose down`/`up` — полный reindex после рестарта не нужен:
  `cbm_cache` (граф SQLite), `claude_context_data` (snapshot/merkle), `milvus_data`+`minio_data`+`etcd_data` (векторы), `ollama_data` (модели).
- `REINDEX_INTERVAL_SEC=0` по умолчанию (cron idle). Не делай `docker compose down -v` — сотрёт кэш.

**Запрещено:** `pkill` контейнерных MCP, `rm` docker volumes / `down -v` наугад, возвращать stdio spawn, параллельный `index_repository` мимо HTTP proxy.

## Health-check

`make zed-search-check` при старте.

- exit 1 → скажи пользователю: запусти `make zed-search` (+ перезапуск IDE, если MCP всё ещё stdio).
- WARN про индекс → `make zed-search-reindex`.

## Команды

- `make zed-search` — Compose up --build + wire + primary index
- `make zed-search-check` / `zed-search-update` / `zed-search-reindex`
- `make zed-search-status` / `zed-search-logs` / `zed-search-down`

## Правило

1. Структура → codebase-memory-mcp.
2. Смысл → claude-context.
3. Литералы → grep.
4. Оба MCP — только через Compose HTTP URL.

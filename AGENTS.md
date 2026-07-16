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

## Стратегия поиска (Cursor + наш стек)

Из [Cursor search docs](https://cursor.com/docs/agent/tools/search): *start specific, then go broad*; exact → grep; concept → semantic then grep; complex → semantic entry points → grep refs → read. У Cursor **нет** рецепта строки `query` для эмбеддера — только выбор стратегии.

У нас цепочка: **граф → семантика → grep → snippet/read**. Concrete symbols лучше vague labels. Explore before changing.

## Формулировка `claude_context_search_code.query`

*Natural language* в схеме тула ≠ копипаст вопроса. Cursor user-prompt («how do we handle X?») выбирает semantic; **агентский `query`** — короткий якорь под чанки кода.

Эмбеддер ранжирует похожесть чанка, не важность файла. Prose/жаргон (`Networkle`, `collect`, `sync`) поднимает skills/prompts раньше ядра (`EntityRepository`, `upload_text`). Признак провала: топ без mutating-кода из `apps/crm` / `core/rag`.

- Короткие якоря (1 мысль, 5–12 слов), термины ближе к коду.
- Один концепт = один вызов; составной вопрос → несколько вызовов.
- Сужай `extensionFilter` (`.py` / `.js`), когда зона известна.
- Плохо: `How does Networkle … What happens if …`
- Хорошо: `CRM note text indexing RAG vector documents` / `EntityRepository upload_text entity_id`
- Мусор в выдаче → не повторяй длинный query; сузь якоря / фильтр или переключись на граф/`grep`.

Полный разбор «почему слабая выдача» — `.cursor/rules/claude-context.mdc` § «Формулировка … query».

## Шпаргалка

1. Имя/regex известны → `grep` (start specific).
2. Структурный вопрос → граф (`trace_path`, `search_graph`, …).
3. По смыслу → `claude_context_search_code` (короткие якоря, не multi-question prose) → затем grep/граф.
4. Тело функции → `get_code_snippet` по qualified_name.
5. Не читай файл-за-файлом, если граф/семантика отвечают за один вызов.
6. Перед правкой — explore existing patterns.

Порядок: **граф → семантика → grep → read**.

## Имя проекта в графе

`list_projects` / `index_status`. Не хардкодь `project`.

## Runtime-канон: Docker Compose

Весь стек — в `scripts/zed_search/docker/docker-compose.yml` (Milvus/etcd/MinIO + CBM+mcp-proxy + claude-context+mcp-proxy).
Ollama embeddings: на macOS — **host Metal GPU** (`OLLAMA_MODE=metal`); docker-профиль — только Linux/CPU.

| Сервис | URL на хосте |
|---|---|
| CBM | `http://127.0.0.1:9751/mcp` + header `X-API-Key` |
| claude-context | `http://127.0.0.1:9752/mcp` + header `X-API-Key` |
| Ollama | `127.0.0.1:11434` (metal: brew/app; docker: контейнер) |
| Milvus | `127.0.0.1:19530` |

- Клиенты Zed/Cursor: только `url` + `headers.X-API-Key` — **не** stdio `command` / `npx`.
- Автоиндексация (без дублей): CBM `auto_index=true` + `auto_watch=true`; claude-context `CLAUDE_CONTEXT_BACKGROUND_SYNC=true`. Cron idle (`REINDEX_INTERVAL_SEC=0`) — не дублирует sync/watch. Полный wipe — `make zed-search-reindex`.
- Репозиторий монтируется по **тому же абсолютному пути**, что на хосте.
- Ключ: `scripts/zed_search/docker/.env` (`MCP_API_KEY`, не коммитить).
- **Named volumes** переживают `compose down`/`up` — полный reindex после рестарта не нужен:
  `cbm_cache` (граф SQLite), `claude_context_data` (snapshot/merkle), `milvus_data`+`minio_data`+`etcd_data` (векторы). `ollama_data` — только при `OLLAMA_MODE=docker`.
- Не делай `docker compose down -v` — сотрёт кэш.

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
2. Смысл → claude-context (короткие якоря в `query`, не multi-question prose).
3. Литералы → grep.
4. Оба MCP — только через Compose HTTP URL.

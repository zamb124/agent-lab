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

## Продуктовый/доменный вопрос → сначала `.mdc`

«Как работает X в сервисе», «что сломается если поменять Y», «откуда берутся данные Z» — **сначала читай `.cursor/rules/<svc>.mdc`** (напр. `crm.mdc`, `rag.mdc`, `flows.mdc`), потом код. Правило даёт модель (источник правды, инварианты, имена символов) за один `read` и превращает дальнейший поиск в точечный `grep`/`get_code_snippet` по уже известным именам. Эмпирика: `crm.mdc` отвечает на «notes ↔ RAG» до любого семантического запроса.

## Стратегия поиска (Cursor + наш стек)

Из [Cursor search docs](https://cursor.com/docs/agent/tools/search): *start specific, then go broad*; exact → grep; concept → semantic then grep; complex → semantic entry points → grep refs → read. У Cursor **нет** рецепта строки `query` для эмбеддера — только выбор стратегии.

У нас цепочка: **rule (`.mdc`) → граф → семантика → grep → snippet/read**. Concrete symbols лучше vague labels. Explore before changing.

### Гочи граф-тулов (стоили вызовов на практике)

- `search_graph.name_pattern` / `search_code.pattern` с `foo|bar` **требуют `regex=true`** — иначе `|` матчится литералом и выдача пустая. Для OR — либо `regex=true`, либо обычный `grep`.
- `trace_path` / `get_code_snippet` по **голому имени** (`create_entity`) → `ambiguous` (несколько совпадений, вызов впустую). Сначала `search_graph`, возьми `qualified_name`, потом трасса/сниппет.

## Формулировка `claude_context_search_code.query`

*Natural language* в схеме тула ≠ копипаст вопроса. Эмбеддер ранжирует cosine чанка, не важность файла; вопрос-prose → шум (skills/prompts/README/CSS/пустые `__init__`).

**Transform вопрос → query (механически, любой домен):**
1. Убери вопросную оболочку: `how/what/why/if`, «как/что/почему/если/что произойдёт».
2. Убери бренды/жаргон: `Networkle`/`Lara`/`Humanitec`/`Linnex`/«сервис»/«collect»/«sync» — они в prompts/skills/docs, не в ядре.
3. Переведи в код-токены: слой/класс (`Repository`/`Service`/`provider`), операция как в коде (`index`/`upload`/`embed`/`search`), данные (`vector_documents`/`entity_id`). Имён не знаешь → возьми из `.cursor/rules/<svc>.mdc`.
4. Один концепт = один вызов; `extensionFilter` когда зона ясна.

**Gate:** можешь назвать символ (из `.mdc`/прошлого поиска)? → `grep`/граф, семантику пропусти. Не запускай семантику с prose в одном батче с чтением правила.

- Плохо: `How does Networkle CRM collect and index notes into RAG?`
- Хорошо: `CRM note text indexing RAG vector documents` / `EntityRepository upload_text entity_id`
- Провал (топ = skills/prompts/README/CSS) → не повторяй query: transform + `extensionFilter`, или граф/`grep`.

Полный разбор — `.cursor/rules/claude-context.mdc` § «Формулировка … query».

## Проверенный fast-path (доменный «как работает X + что сломается при Y»)

1. `read .cursor/rules/<svc>.mdc` — модель ответа + имена символов.
2. `grep` по известному литералу из правила (напр. `upload_text`, `vector_documents`) в зоне (`apps/<svc>`).
3. `get_code_snippet` по qualified_name на точке мутации (create/update) + на входе данных (напр. `resolve_note_text`).
4. `read` фонового пути, который вопрос затрагивает (напр. `reembed_stale_documents`).

Широкая семантика тут не нужна — правило + grep по литералу точнее и дешевле.

## Шпаргалка

1. Доменный/продуктовый вопрос → сначала `.cursor/rules/<svc>.mdc`.
2. Имя/regex известны → `grep` (start specific).
3. Структурный вопрос → граф (`trace_path`, `search_graph`, …); `qualified_name` из `search_graph`, `|` только с `regex=true`.
4. По смыслу → `claude_context_search_code` (короткие якоря, не multi-question prose) → затем grep/граф.
5. Тело функции → `get_code_snippet` по qualified_name.
6. Не читай файл-за-файлом, если rule/граф/семантика отвечают за один вызов.
7. Перед правкой — explore existing patterns.

Порядок: **rule → граф → семантика → grep → read**.

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

## MCP — опционально

Не запускай `make zed-search-check` «при старте». Тулы MCP есть в сессии — пользуйся; нет / падают — `grep`/`Glob`/`Read`, без требования поднять стек. `make zed-search*` — только по явной просьбе или при починке поиска.

## Команды

- `make zed-search` — Compose up --build + wire + primary index (wire также пишет Zed `agent.tool_permissions`: default allow, fetch/search_web/edit — allow, delete/move — confirm, terminal — confirm на `sudo`/`git push`/`rm -rf`)
- `make zed-search-check` / `zed-search-update` / `zed-search-reindex` (ручные)
- `make zed-search-status` / `zed-search-logs` / `zed-search-down`

## Правило

1. MCP доступен → структура через codebase-memory-mcp; иначе grep/Glob.
2. MCP доступен → смысл через claude-context (короткие якоря в `query`, не multi-question prose); иначе grep.
3. Литералы → grep.
4. Оба MCP — только через Compose HTTP URL (когда подключены).

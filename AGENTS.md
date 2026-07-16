# Поиск по коду — два движка

В проекте два независимых поиска. Не заменяй один другим — у них разные задачи.

- **codebase-memory-mcp** — структурный граф знаний (tree-sitter AST + Hybrid LSP → SQLite). 158 языков: call graph, импорты, наследование, HTTP-маршруты, dead code, архитектура. Локальный, без Docker/API.
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

Для структурных вопросов **сначала граф** — не file-by-file `read`. Граф отвечает за один вызов и экономит ~99% токенов vs grep/read-циклов.

## Что и когда эффективно (шпаргалка для агента)

Выбор инструмента = вопрос + что знаешь. Короткие правила:

1. **Знаешь имя/regex и где искать** → `grep`. Точнее и быстрее семантики, ноль ложных срабатываний.
2. **Структурный вопрос** (кто вызывает, impact, dead code, архитектура, маршруты, импорты, наследование) → **граф** (`trace_path`, `search_graph`, `query_graph`, `get_architecture`, `get_code_snippet`). Один вызов вместо обхода файлов.
3. **По смыслу, без точных имён** (где реализован X, как работает Y, всё про Z; поиск по докам/конфигам/комментариям) → `claude_context_search_code`. Если сломан — fallback на `grep`, но качество хуже.
4. **Нужно прочитать тело функции** → `get_code_snippet` по qualified_name из графа, не `read_file` вслепую.
5. **Файлы по имени/шаблону** → `find_path`.
6. **Никогда не читай файл-за-файлом `read`, если граф или семантика отвечают за один вызов.** Это сжигает токены и время.

Порядок: **граф → семантика → grep → read**. Спускайся вниз только когда верхний уровень не дал ответа.

Если не уверен, какой инструмент — для структурного вопроса бери граф, для смыслового — семантику, для точной строки — grep.

## Имя проекта в графе

Тулы графа требуют `project`. Не хардкодь — узнавай через `list_projects` (разрешён, мгновенно). Для статуса/свежести индекса — `index_status`.

## Health-check при старте

Перед первой задачей по коду запусти `make zed-search-check` (claude-context MCP):

- **exit 0** — MCP работает. Используй `claude_context_search_code` для семантики.
- **exit 1** — claude-context сломан. Сообщи пользователю первым сообщением:
  > ⚠️ claude-context MCP не работает — семантический поиск недоступен.
  > Запусти `make zed-search` для настройки (Ollama + Milvus + автоиндексация).
  > Граф codebase-memory-mcp независим от Milvus — структурные запросы продолжат работать.
  Для семантики временно через grep, но хуже по качеству.
- **WARN (exit 0)** — обработай каждый WARN:
  - **MCP-пакет устарел** — `make zed-search-update`, перезапусти Zed.
  - **Индекс устарёл/отсутствует** — `make zed-search-reindex`.
  - Другие WARN — сообщи кратко и продолжай.

codebase-memory-mcp health-check не нужен (локальный SQLite, без внешних зависимостей). Если `list_projects` пуст или проект отсутствует — переиндексируй командой ниже.

## Команды

claude-context MCP:
- `make zed-search-check` — health-check (exit 0/1 + WARN).
- `make zed-search-update` — обновить MCP-пакет.
- `make zed-search-reindex` — переиндексировать для семантики.
- `make zed-search` — полная настройка (Ollama + Milvus + автоиндексация).

codebase-memory-mcp:
- `codebase-memory-mcp cli list_projects` — проиндексированные проекты.
- `codebase-memory-mcp cli index_repository '{"repo_path":"<абсолютный_путь>"}'` — (пере)индексировать граф.
- `codebase-memory-mcp cli <tool> '<json>'` — любой тул из CLI.
- `codebase-memory-mcp config set auto_index true` — автоиндекс при старте сессии.
- `codebase-memory-mcp update` — обновить бинарь.

## Правило

1. Структурные вопросы (кто кого вызывает, impact, архитектура, dead code, маршруты, импорты) — **сначала codebase-memory-mcp**.
2. Семантические вопросы (по смыслу, без точных имён; по не-кодовому тексту/докам/конфигам) — **claude_context_search_code**.
3. Точные литералы/regex — `grep`.
4. Не обходи код file-by-file `read`, если граф или семантика могут ответить за один вызов.

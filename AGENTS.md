# Агентам: вход в репозиторий

Канон — `.cursor/rules/`: конституция `main.mdc`, взаимодействие `architecture.mdc`, канон самих правил `rules.mdc`, домены — `<домен>.mdc`. Процедуры — `.cursor/skills/`: выравнивание кода под канон — `refactor-engineer`, backend — `backend-engineer`, UI — `frontend-engineer`, прод и релизы — `devops-engineer`, новый сервис — `new-service`, tools — `design-flow-tools`, UI-документация — `documentator`.

## Поиск по коду

Порядок: правило → граф → семантика → grep → чтение. Инструменты и формулировка запросов → `.cursor/rules/code_search.mdc`.

1. Продуктовый или доменный вопрос — сначала `.cursor/rules/<домен>.mdc`: модель, инварианты и имена символов; дальше точечный `rg` по этим именам.
2. Структура (кто вызывает, импорты, маршруты, dead code) — граф `codebase-memory-mcp`: `search_graph`, `trace_path`, `query_graph`, `get_code_snippet`, `get_architecture`, `get_graph_schema`, `search_code`. Проект — абсолютный путь репозитория, где `/` заменён на `-`, без ведущего дефиса: `Users-viktor-shved-PycharmProjects-agent-lab`.
3. Поиск по смыслу без точных имён — `claude-context` (`search_code`); запрос — короткие код-токены, не вопрос прозой.
4. Известное имя или литерал — `rg`.
5. MCP опционален: нет инструментов — `rg`, Glob, Read.

## Команды

- `make app` — сборка UI и все сервисы локально (mprocs, esbuild watch — процесс `ui_watch`); `make app APP_KILL=1` — освободить порты перед стартом.
- `make lint` — все гейты; `make lint <path>` — один файл; `make lint-ts` — frontend.
- `make test-up` — сборка UI, тестовый стек и миграции, обязателен до `pytest`; `uv run pytest tests/<домен>/ -q` — домен; `make test` — всё.
- `make migrate` — миграции dev-баз.
- `uv add <pkg>`, `uv sync`, `uv run python <file>` — зависимости и запуск.
- `make doc`, `make doc-serve` — портал документации.

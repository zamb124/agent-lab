# Discovery

Порядок: правило → гейты → детекторы классов → граф → `rg` → чтение тела. Каждая находка проверяется чтением кода и правила-владельца; совпадение регэкспа — только кандидат.

## Baseline

```bash
git status --porcelain > /tmp/refactor_preflight_status.txt
uv run python .cursor/skills/refactor-engineer/scripts/gates_report.py /tmp/refactor_gates_before
uv run python .cursor/skills/refactor-engineer/scripts/ratchet_list.py --top 5
uv run python -m scripts.gates.repo.rules_drift
rg -n "\[без гейта\]" .cursor/rules
```

- `gates_report.py` — шаги `_lint-py` и `lint-ts` из `mk/lint.mk` по отдельности (5–10 минут из-за basedpyright); сводка — `summary.txt`, лог шага — `NN_<step>.log`.
- `ratchet_list.py <metric>` — все `файл:строка` метрики; без аргумента — «текущее / baseline» и топ файлов. Текущее ниже baseline — лимит не подтянут: `uv run python -m scripts.gates.backend.ratchet_counts --update`.
- `rules_drift.py` — мёртвые пути в правилах и скилах, ссылки на несуществующие `.mdc` в коде и доках, ссылки `§ <Раздел>` без заголовка, разделы `##` вне шаблона или не по порядку, запрещённые слова, frontmatter, globs без совпадений, бюджеты размера.
- `analyze_imports.py` печатает `Total local imports: N`; нарушение — `N > 0` независимо от кода выхода.

## Граница запуска

- Домен — `.cursor/rules/<домен>.mdc`: globs правила задают файлы домена, раздел «Модель» — канонические имена.
- Сервис — `apps/<svc>/`, воркер — `apps/<svc>/worker.py` (второй — `worker_<name>.py`; idle — `apps/idle/`), модели и сервисы домена в `core/<domain>/`, тесты `tests/<svc>/`.
- Класс нарушения — детектор из `references/violation-catalog.md` по всему `apps/` и `core/`.

## Граф codebase-memory-mcp

Проект — абсолютный путь репозитория, где `/` заменён на `-`, без ведущего дефиса: `Users-viktor-shved-PycharmProjects-agent-lab`. `file_path` в графе относительный (`apps/...`). Нет MCP — `rg`, Glob, Read.

- Кто вызывает: `search_graph(name_pattern="^op_pages_create$")` → `qualified_name` → `trace_path(function_name=<qualified_name>, direction="inbound")`.
- Тело функции: `get_code_snippet(qualified_name=...)`.
- Dead code:

```cypher
MATCH (f:Function) WHERE f.file_path STARTS WITH 'apps/' AND NOT EXISTS { (f)<-[:CALLS]-() }
RETURN f.qualified_name, f.file_path LIMIT 200
```

- Делегат-обёртки (кандидаты на запрет 12): функции с одним исходящим вызовом.

```cypher
MATCH (f:Function)-[:CALLS]->(g) WHERE f.file_path STARTS WITH 'apps/'
WITH f, count(g) AS calls WHERE calls = 1
RETURN f.qualified_name, f.file_path LIMIT 200
```

- Самые сложные функции среза: `MATCH (f:Function) WHERE f.file_path STARTS WITH 'apps/<svc>/' RETURN f.qualified_name, f.complexity ORDER BY f.complexity DESC LIMIT 20`.
- `name_pattern` с `|` требует регулярного выражения; голое имя в `trace_path` неоднозначно — сначала `search_graph`.

## Дрейф правил (режим `rules`)

1. `uv run python -m scripts.gates.repo.rules_drift` — список нарушений канона `rules.mdc`.
2. Для каждого мёртвого пути найти фактическое место символа (`rg -n "class <Name>|def <name>" apps core`) и исправить правило as-is; символа нет нигде — удалить упоминание.
3. Ссылка из кода на несуществующее правило — заменить на правило-владельца из `main.mdc` § Навигация.
4. Норма правила противоречит коду — определить, что нарушено: код (срез `slice`) или правило (исправить as-is); узаконивать нарушение правкой правила запрещено.

## Метки `[без гейта]` (режим `gate`)

`rg -n "\[без гейта\]" .cursor/rules` — нормы без детектора. Приоритет — порядок P0–P5 из `SKILL.md`; внутри приоритета — норма из `main.mdc` § Запреты приоритетнее доменной. Порядок работы — `references/playbooks.md` § Добавить детектор.

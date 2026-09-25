# Каталог нарушений

Класс → норма-владелец → детектор → целевая форма. Детектор без гейта — кандидат для режима `gate` (`references/playbooks.md` § Добавить детектор). Паттерны дают кандидатов; решение — после чтения тела, вызывающих и правила-владельца. Внешняя граница (`main.mdc` § Внешняя граница) и пункты `Исключение:` правил нарушением не являются. Команды запускаются из корня репозитория.

## L — слои

**L1. Модель, объектный Check или ветки сценария в `op_*`.** Норма: `main.mdc` § Куда писать код; `architecture.mdc` § Операция op_*. Цель: `op_*` = scope + один метод сервиса; Check, ветки и not-found — в сервисе.

```bash
rg -n 'await [A-Z]\w+\.(get|objects|by_|for_|list|require_|find_|alive_)' apps/*/realtime
rg -n 'require_can_|authz_service\.(check|require)' apps/*/realtime
```

**L2. `objects`, `execute_raw`, `atomic` вне модели.** Норма: `main.mdc` § Куда писать код, запрет 17. Цель: `@classmethod` на модели-владельце; сервис зовёт `await Model.method(...)`.

```bash
rg -n '\.objects\.|execute_raw\(|\batomic\(' apps core -g '*.py' -g '!**/models/**' -g '!**/models.py' -g '!core/db/**'
```

**L3. Право, событие, HTTP, задача в модели.** Норма: `main.mdc` § Куда писать код. Цель: метод сервиса.

```bash
rg -n 'publish_event|require_can_|ServiceClient|httpx|enqueue\(' -g '**/models/**' -g '**/models.py' apps core
```

**L4. `handlers.py` и свободные функции со смыслом сценария.** Норма: `main.mdc` § Куда писать код. Цель: метод сервиса с именем логики.

```bash
rg --files apps core | rg 'handlers\.py$'
```

## M — модели Oxyde

**M1. Таблица вне `models/<entity>.py` или несколько таблиц в файле.** Норма: запрет 17; `database.mdc`. Цель: один файл `models/<entity>.py` на таблицу. Паттерн видит прямых наследников `PlatformModel`; косвенных — через базовый класс сервиса.

```bash
rg -c '^class \w+\(.*PlatformModel' apps core -g '*.py' | awk -F: '$2 > 1 || $1 !~ /\/models(\/|\.py)/'
```

**M2. Каталог `apps/<svc>/db/`.** Норма: `main.mdc` § Стандарт сервиса. Цель: таблицы — `models/`, DB-примитивы — `core/db/`.

```bash
ls -d apps/*/db apps/flows/src/db 2>/dev/null
```

**M3. `*Repository`, `TableRepository`, `*_queries.py`, `db/repositories/`.** Норма: запрет 17. Цель: `@classmethod` на модели.

```bash
rg -n 'class \w+Repository\b|TableRepository|db/repositories' apps core -g '*.py'
rg --files apps core | rg '_queries\.py$'
```

**M4. Имя метода модели вне семейства.** Норма: `database.mdc` § Имена методов. Цель: семейство по смыслу → `references/playbooks.md` § Контракты методов модели.

```bash
rg -n 'def (get_by|find|load|fetch|read|save|remove)_\w+' -g '**/models/**' -g '**/models.py' apps core
```

**M5. Миграция кроме `0001_initial.py`.** Норма: `database.mdc`. Цель: одна ревизия на базу.

```bash
rg --files migrations | rg -v '/0001_initial\.py$|services\.json$|__init__\.py$'
```

## D — композиция процесса

**D1. `dependencies.py`, `container.py`, `components.py`, `get_*_service()`.** Норма: запрет 18; `architecture.mdc` § Service Kit DI. Цель: поле `<Process>Di`, recipe в `di.py`.

```bash
rg --files apps core | rg '/(dependencies|container|components)\.py$'
rg -n '^def get_\w+_service\(' apps core
```

**D2. Module-global singleton.** Норма: `architecture.mdc` § Service Kit DI и его «Исключения» (`set_billing_service`). Цель: компонент DI.

```bash
rg -n '^\s*global \w+' apps core -g '*.py'
rg -n '^_\w+: .*\| None = None$' apps core -g '*.py'
```

**D3. `di` внутри service, model, runtime, client.** Норма: `architecture.mdc` § Service Kit DI. Детектор: `uv run python scripts/check_dependency_injection_canon.py`. Цель: конкретный компонент через constructor.

## T — транспорт и ошибки

**T1. REST-хендлер без `op_*`.** Норма: `architecture.mdc` § REST-зеркало. Детектор: `uv run python scripts/check_rest_handlers_call_ops.py`. Цель: payload → тот же `op_*`.

**T2. `HTTPException` в `apps/`.** Норма: `architecture.mdc` § Ошибки границы. Цель: `raise_*` или `Platform*Error`.

```bash
uv run python .cursor/skills/refactor-engineer/scripts/ratchet_list.py http_exception_in_services
```

**T3. App-level код в `main.py`.** Норма: `architecture.mdc` § App-level поведение. Цель: параметры `create_service_app`.

```bash
rg -n '@app\.exception_handler|app\.add_middleware|on_startup|on_shutdown' apps -g 'main.py'
```

**T4. Команда без каталога владельца или без REST-зеркала фабрики.** Норма: `architecture.mdc` § Транспорт. Детекторы: `scripts/check_command_owner_catalogs.py`, `scripts/check_command_rest_mirror.py`. Цель: `<SVC>_OPERATIONS` + REST route + `restMirror`.

**T5. Свой класс ошибки без дополнительных атрибутов.** Норма: `architecture.mdc` § Ошибки границы. Цель: `core/errors/boundary.py`.

```bash
rg -n 'class \w+(NotFound|Conflict|AccessDenied|Forbidden)Error\b' apps
```

## X — перевод и дубли контрактов

**X1. Mapper.** Норма: запрет 11. Цель: общий нативный тип; конвертация — только на внешней границе.

```bash
rg -n '^\s*(async )?def (\w+_to_\w+|\w*_from_\w+|(convert|map|adapt|normalize)_\w+|to_dict|from_dict)\(' apps core -g '*.py'
rg --files apps core | rg '/(mapping|mappers|adapters|converters|translators)\.py$'
```

**X2. Twin-модель.** Норма: запрет 13. Цель: одна модель; отдельная — только при другой форме. Подтверждение — сравнение полей с канонической моделью сущности.

```bash
rg -n '^class \w+(DTO|Data|Internal|Response|Info|View)\(' apps core -g '*.py'
```

**X3. Метод-делегат, wrapper, alias, re-export.** Норма: запрет 12. Цель: прямой вызов канонического метода. Граф: функции с одним вызовом → `references/discovery.md` § Граф.

```bash
rg -n '^\s*return await (self|cls)\.\w+\(' apps core -g '*.py'
```

## C — границы сервисов

**C1. Импорт `apps/<a>` → `apps/<b>`.** Норма: `main.mdc` § Границы core и apps. Детектор: `uv run python scripts/check_cross_service_imports.py`. Цель: общее — `core/`, владелец — `core/clients/` или его модель.

**C2. Клиент вне `core/clients/`, прямой `httpx`.** Норма: `main.mdc` § Границы core и apps; `architecture.mdc` § Межсервисный доступ. Цель: typed клиент в `core/clients/` поверх `ServiceClient`.

```bash
rg --files apps | rg '/clients/'
rg -n 'httpx\.(AsyncClient|Client)\(' apps -g '*.py'
```

**C3. Копипаста между сервисами.** Норма: запрет 16. Цель: модуль в `core/`.

```bash
uv run python - <<'EOF'
import collections, difflib, itertools, pathlib
skip = {"__init__.py", "config.py", "di.py", "main.py", "events.py", "command_router.py", "operations.py"}
groups = collections.defaultdict(list)
for path in pathlib.Path("apps").rglob("*.py"):
    parts = path.relative_to("apps").parts
    if "__pycache__" in parts or len(parts) < 2 or path.name in skip:
        continue
    groups["/".join(parts[1:])].append(path)
for inner, paths in sorted(groups.items()):
    for left, right in itertools.combinations(paths, 2):
        ratio = difflib.SequenceMatcher(None, left.read_text(), right.read_text()).quick_ratio()
        if ratio > 0.85:
            print(f"{ratio:.2f}  {left}  {right}")
EOF
```

**C4. Одинаковые boundary-хелперы.** Норма: запрет 16. Цель: хелпер `core/request_scope.py`.

```bash
rg -n '^(async )?def _(scope|require_\w+)\(' apps -g '*.py'
```

## S — строгость

**S1. `cast`, `object`, `Any`, `# type: ignore`.** Норма: запрет 8; `main.mdc` § Типизация. Цель: тип в источнике → `references/playbooks.md` § Первопричина потери типа.

```bash
uv run basedpyright --level warning --warnings apps core
uv run python .cursor/skills/refactor-engineer/scripts/ratchet_list.py cast_calls
rg -n '\bAny\b' apps core -g '*.py'
```

**S2. `getattr(obj, "x", default)`.** Норма: запрет 7. Детектор: `uv run python scripts/audit_wider_repo_strictness.py`. Цель: прямой доступ к атрибуту типизированной модели.

**S3. `value or "default"`.** Норма: запрет 7. Цель: `raise` при отсутствии; дефолт — в Pydantic-модели.

```bash
rg -n '=\s*[\w.\[\]"'"'"']+\s+or\s+("|'"'"'|\[|\{|0\b|None\b)' apps core -g '*.py'
```

**S4. Проглоченное исключение, широкий `try`.** Норма: запреты 1–3. Цель: `try` только вокруг IO, `raise ... from e`.

```bash
uv run python .cursor/skills/refactor-engineer/scripts/ratchet_list.py except_pass
rg -n 'except Exception' apps core -g '*.py'
```

**S5. Локальный импорт.** Норма: запрет 4. Детектор: `uv run python analyze_imports.py` — нарушение, если `Total local imports` больше 0. Цель: импорт на уровне файла, цикл — перестройкой слоёв.

**S6. `os.environ`, `os.getenv`.** Норма: `configuration.mdc`. Детектор: `ratchet_list.py os_environ`. Цель: Pydantic Settings.

**S7. `print`, голый `asyncio.create_task`.** Норма: `logging.mdc`. Цель: `get_logger`, платформенный запуск фоновых задач.

```bash
make check-logging
rg -n '^\s*print\(|asyncio\.create_task\(' apps core -g '*.py'
```

## Y — layout

**Y1. Нестандартный файл или каталог сервиса.** Норма: `main.mdc` § Стандарт сервиса.

```bash
for d in apps/*/; do echo "$d: $(ls "$d" | tr '\n' ' ')"; done
```

**Y2. Пакет `apps/flows/src/*` вне whitelist.** Норма: `flows.mdc` § Layout. Цель: клиенты — `core/clients/`, таблицы — `models/`, middleware — `core/middleware/`, контракты — модуль-владелец.

```bash
ls apps/flows/src | rg -v -x 'a2a|agent|api|channels|durable_execution|evaluation|files|models|observability|registry|resources|runners|runtime|services|state|streaming|tasks|tools|triggers|events\.py|__init__\.py|__pycache__'
```

**Y3. Каталог `apps/` вне таблицы сервисов.** Норма: `main.mdc` § Стандарт сервиса, § Сервисы и стек. Детектор: `ls apps`. Цель: процесс из таблицы; тестовый стенд — `tests/`.

## N — имена

**N1. Голые `id`/`type` в доменной модели.** Норма: `main.mdc` § Именование. Цель: `<entity>_id`, `<entity>_type` или `kind`.

```bash
rg -n '^\s+(id|type): ' -g '**/models/**' -g '**/models.py' apps core
```

**N2. Запрещённые синонимы.** Норма: `main.mdc` § Именование.

```bash
rg -n '\b(tenant_id|workspace_id|org_id|space_id|attrs)\b' apps core -g '*.py'
```

## Q — тесты

**Q1. `AsyncMock`, `monkeypatch` внутренних компонентов, `skip`.** Норма: `testing.mdc`. Цель: реальная инфраструктура, единственный мок — `MockLLM`.

```bash
uv run python .cursor/skills/refactor-engineer/scripts/ratchet_list.py tests_asyncmock
uv run python .cursor/skills/refactor-engineer/scripts/ratchet_list.py tests_monkeypatch_internal
uv run python .cursor/skills/refactor-engineer/scripts/ratchet_list.py tests_skip_markers
```

**Q2. Фейк внутреннего компонента.** Норма: `testing.mdc`. Цель: реальный компонент из DI фикстуры.

```bash
rg -n '^class (InMemory|Fake|Stub)\w+' tests -g '*.py'
```

## F — frontend

**F1. Нарушения UI-канона.** Нормы: `frontend.mdc`, `ui_factories.mdc`, `ui_components.mdc`, `ui_fields.mdc`. Детекторы: `make check-events-canon`, `make check-field-canon`, пункты `scripts/check_ui_canon.sh`. Цель: фабрика, helper базы, core-компонент.

**F2. Текст вне i18n.** Норма: `frontend.mdc`.

```bash
make check-i18n-keys
uv run python scripts/report_ui_i18n_gaps.py --app <svc>
```

## R — правила

**R1. Мёртвый путь, ссылка на несуществующее правило или раздел, раздел вне шаблона, стоп-слово, frontmatter, бюджет.** Норма: `rules.mdc`. Цель: правило as-is по шаблону.

```bash
python3 .cursor/skills/refactor-engineer/scripts/rules_drift.py
```

**R2. Норма без детектора.** Норма: `rules.mdc` § Канон, п. 7. Цель: детектор в `scripts/`.

```bash
rg -n '\[без гейта\]' .cursor/rules
```

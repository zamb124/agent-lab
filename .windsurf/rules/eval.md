---
trigger: model_decision
description: "Eval sandbox: безопасное исполнение тулов, namespace whitelist, паттерн создания тулов"
globs:
---
# Eval Sandbox — безопасность и паттерны

## Модель безопасности

Код тула = **публичный код**. Его может редактировать внешний разработчик через UI редактора flows. Поэтому:

- Тул исполняется в **sandbox** (`PythonNamespaceBuilder` → `exec` в ограниченном namespace).
- Sandbox видит **только whitelist** имён. Всё остальное недоступно.
- Платформенные сервисы (`core/`, `apps/`) = **защищённый внутренний код**, недоступный напрямую.

Доступ из тула к платформе — **только через узкие фасады** (`platform_services.py`), зарегистрированные в namespace.

## АБСОЛЮТНЫЕ ЗАПРЕТЫ в пользовательском коде тулов

1. **Прямой обход `platform_services` в кастомном коде** (хранимом в БД): не импортировать `get_container` к DI. Платформа регистрирует `get_code_runner` (без `FlowContainer`) в sandbox ради паритета `sandbox_codegen`; это не разрешение обходить фасады в новом кастомном туле. Канон: **`.cursor/rules/eval.mdc`**.
2. **Импорты `apps.*` / `core.*`** — вырезаются; без strip ломается sandbox.
3. **Импорты между модулями тулов** — вырезаются как `apps.*`.
4. **Прямой `httpx.AsyncClient` к сервисам платформы** — только `ServiceClient`.

## Жизненный цикл кода тула

```
@tool(name="my_tool", ...)     ← Python-модуль в apps/flows/tools/
        │
        ▼
load_tools_to_db               ← inspect.getsource → strip imports → tool_repository (БД)
        │
        ▼
FlowsLoader._inline_single_tool ← код из БД инлайнится в flow config (поле code)
        │
        ▼
ToolRegistry.materialize        ← видит code → CodeTool (sandbox exec)
        │
        ▼
PythonNamespaceBuilder.build()  ← whitelist namespace
        │
        ▼
exec(code, namespace)           ← код тула исполняется С ЭТИМ namespace
```

**Следствие:** любая зависимость, которой нет в namespace, даст `NameError`. Импорты `apps.*`/`core.*` вырезаны. Тул должен быть **самодостаточен** в рамках namespace.

## Паттерн: как писать тул

### Хелпер нужен ТОЛЬКО этому тулу

Определить **внутри тела функции** (как `_pick_file` в `read_file`):

```python
@tool(name="my_tool", ...)
async def my_tool(arg: str, state: Optional[dict] = None) -> dict:
    def _helper(x):
        return x.strip().lower()

    return {"result": _helper(arg)}
```

### Хелпер нужен НЕСКОЛЬКИМ тулам

1. Добавить в `apps/flows/src/eval/state_utils.py`
2. Зарегистрировать в `apps/flows/src/eval/namespace.py` (`namespace["helper_name"] = helper_name`)
3. Использовать в тулах как глобальное имя (оно уже в namespace при sandbox exec)
4. Для FunctionTool-пути (прямой вызов builtin) — дополнительно определить inline-копию внутри функции

Пример: `find_file` (поиск файла в `state.files`), `_extract_ids_from_state`, `_require_context_namespace`.

### Доступ к платформенному сервису

1. Добавить **фасад** в `apps/flows/src/eval/platform_services.py`
2. Зарегистрировать в `namespace.py`
3. Вызывать из тула по имени фасада

Существующие фасады: `get_oauth_service`, `get_file_bytes`, `get_schedule_service`, `get_operator_handoff_service`, `get_google_oauth_token`, `get_lara_facade`, `get_code_runner`.

## Состав namespace (SSOT)

Не дублировать длинные списки здесь. Канон и таблица ссылок: **`.cursor/rules/eval.mdc`**, код: `apps/flows/src/eval/namespace.py`, проверка: `make check-inline-docs`, справка: `core/docs/data/python/globals.py`.

### Чего нет (кроме whitelist)
`get_settings`, `Path`, `os`, `sys`, `subprocess`, `socket` и т.д. `get_code_runner` / codegen-имена могут быть в namespace как платформенная регистрация — см. **`.cursor/rules/eval.mdc`**.

### Валидация AST (`compiler._validate_code`)
Доступ к атрибутам вида `__*__` (например `obj.__name__`, `obj.__class__`) в коде тулов **запрещён**. Имя типа исключения: `getattr(type(exc), "__name__", "")` (имя атрибута — строковый литерал, не `ast.Attribute`).

## ОБЯЗАТЕЛЬНО: актуализация документации внешнего разработчика

При **любом** изменении namespace, eval-окружения или добавлении тула — **сразу** актуализировать документацию в `core/docs/data/python/`:

| Изменение | Что актуализировать |
|-----------|-------------------|
| Новая функция/объект в namespace | `globals.py` — добавить запись с `name`, `type`, `doc` |
| Новый фасад в `platform_services.py` | `globals.py` — добавить запись |
| Изменение сигнатуры существующего | `globals.py` — обновить `doc` |
| Новый модуль в `ALLOWED_IMPORT_ROOTS` | `modules.py` (подхватится автоматически) + `MODULE_METHODS` если нужны подсказки |
| Новый builtin | `core/inline_python_eval_policy.py` (подхватится автоматически) |
| Новый паттерн использования | `templates.py` — добавить шаблон с примером кода |

**Без актуализации `core/docs` изменение НЕ считается завершённым.** Внешний разработчик видит только то, что описано в `core/docs` — если функция есть в namespace, но нет в документации, для него она не существует.

## Чеклист: добавление нового тула

1. Модуль в `apps/flows/tools/` с декоратором `@tool`
2. Pydantic `args_schema` с `Field(description=...)` — обязательно
3. **Никаких импортов `apps.*` / `core.*` в теле функции** — они будут вырезаны
4. Хелперы — **внутри тела функции** или через namespace (`state_utils.py`)
5. Платформенные сервисы — **только через фасады** (`platform_services.py`)
6. Имя в `apps/flows/tools/__init__.py` → `__all__`
7. Регистрация в `ToolRegistry.register_builtin_tools`
8. `mock_response` для тестового режима
9. **Актуализировать `core/docs/data/python/globals.py`** — если тул добавляет глобалы в namespace

## Ключевые файлы

| Файл | Назначение |
|------|-----------|
| `apps/flows/src/eval/namespace.py` | `PythonNamespaceBuilder` — whitelist namespace |
| `apps/flows/src/eval/state_utils.py` | Утилиты для inline-кода (find_file, get_files, ask_user, ...) |
| `apps/flows/src/eval/platform_services.py` | Узкие фасады к платформенным сервисам |
| `apps/flows/src/eval/compiler.py` | Компиляция и валидация кода |
| `apps/flows/src/eval/import_policy.py` | Whitelist импортов (`safe_inline_import`) |
| `apps/flows/src/eval/inline_tool_sanitize.py` | `strip_forbidden_platform_import_lines` |
| `core/inline_python_eval_policy.py` | `ALLOWED_BUILTINS` |
| `apps/flows/tools/` | Реализации тулов (публичный код) |
| `apps/flows/tools/__init__.py` | `__all__` — экспорт имён в namespace |

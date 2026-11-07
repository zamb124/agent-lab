# Playbooks

Рецепт = шаги одного среза. Каждый срез проходит цикл `SKILL.md`: контракт среза → детектор → правка → проверка → правило-владелец → отчёт. Нормы — в правилах; здесь только порядок действий.

## Тонкий `op_*`

Когда: L1 из каталога — `op_*` зовёт модель, делает объектный Check, ветвит сценарий или превращает `None` в not-found.

1. Выбрать граница-файл `apps/<svc>/realtime/<area>operations.py` или одно семейство verb одной сущности.
2. Для каждого `op_*` выписать: scope (хелпер `core/request_scope.py`), аргументы из payload, вызываемые модели и сервисы, ветки, Check, превращения ошибок.
3. Найти метод сервиса с именем логики; нет — создать в `apps/<svc>/services/<entity>_service.py` (или в `core/<domain>/service.py`, если домен в `core`). Перенести туда Check (`authz_service.require_*`), ветки, вызовы моделей, `PlatformNotFoundError`.
4. `op_*` оставить формой `main.mdc` § Куда писать код: scope → один метод сервиса → результат; `Platform*Error` → `raise_*` только ради своего `detail`.
5. Воркеры, ноды, tools, которые повторяли ту же логику, переключить на тот же метод сервиса.
6. Тесты: `tests/realtime/test_<svc>_commands.py` (WS ≡ REST), тесты сервиса на Check и not-found.

Ловушка: helper `_scope` сервиса, который делает объектный Check, — это сценарий; Check уходит в сервис, `_scope` заменяется хелпером `core/request_scope.py`.

## SQL из сервиса в модель

Когда: L2 — `objects`, `execute_raw`, `atomic` в сервисе, `op_*` или API.

1. Для каждого вызова `objects` определить модель-владельца результата и смысл запроса (ключ, кардинальность, запись) → имя по `database.mdc` § Имена методов.
2. Существующий метод модели с тем же смыслом — использовать его. Нет — добавить `@classmethod` на модели (`cls.objects`), один атомарный шаг.
3. `atomic` остаётся на модели, если это шаг записи сущности и её непосредственных строк; иначе сценарий в сервисе вызывает несколько методов моделей, а транзакционную границу держит метод модели-агрегата.
4. Сохранить filters, ordering, limits, locks, `using`, conflict behavior, company scope (`__global_model__` — явный фильтр `company_id`).
5. Удалить прямые `objects` из сервиса; `rg` по границе — 0.

## Таблица в `models/<entity>.py`

Когда: M1, M2 — таблица в `db/models.py`, несколько таблиц в одном файле, `apps/<svc>/db/`.

1. Одна таблица — один файл `apps/<svc>/models/<entity>.py` (flows — `apps/flows/src/models/`, домен в `core` — `core/<domain>/models/<entity>.py`), класс и его `@classmethod`-запросы переносятся без изменения поведения.
2. Импорты всех потребителей (сервисы, api, realtime, tests, backfill, scripts) — на новый путь; re-export из заменённого модуля не оставлять.
3. `migrations/services.json`: `models_module` указывает на пакет с моделями; `uv run python -m scripts.db.migrate --help` и тесты миграций подтверждают discovery.
4. `scripts/gates/backend/cross_service_imports.py` разрешает `apps.<svc>.models.*` — импорт peer-моделей из `db` заменяется на `models`.
5. Непустой `apps/<svc>/db/` после переноса — только DB-примитивы; они переезжают в `core/db/`, каталог удаляется.
6. Проверка: `make test-up` (миграции поднимаются), `uv run pytest tests/<svc>/ -q`.

## Контракты методов модели

Когда: режим `models`, M4 — одинаковый смысл под разными именами или одно имя с разным смыслом.

1. Прочитать базовый контракт `PlatformModel` (`core/models/platform_model.py`): generic PK CRUD уже есть — не дублировать.
2. Для каждого кандидата заполнить карточку по телу метода и вызывающим:

```text
owner, current_name, key_kind (primary|natural|composite|foreign|predicate),
cardinality (optional_one|required_one|many|count), write_semantics (read|insert|insert_once|
pk_upsert|natural_upsert|partial_update|transition|append|hard_delete|soft_delete),
return_contract, error_contract, idempotency, tenant_scope, database_alias, callers, canonical_name
```

3. Имя — по `database.mdc` § Имена методов. Смысл не установлен по телу и вызывающим — метод не переименовывается.
4. Приоритет: override generic-имени с другой семантикой → один смысл с разными return/error → два публичных имени одного запроса → синонимы PK CRUD → natural/composite key → list/transition/append/delete.
5. В одном срезе не смешивать: optional → required и удаление PK-override; hard delete и soft delete/revoke; PK upsert и append/version; tenant-scope и naming.
6. Сменить имя и сигнатуру, обновить всех вызывающих, тесты, фикстуры; убрать заменённое имя, re-export, `__all__`. `0 rows` не превращается в ошибку и обратно без полной миграции контракта.
7. Тесты по контракту: optional — найдено/нет; required — найдено/точный not-found; create — успех/конфликт; insert-once — вставлено/уже есть; upsert — вставка/обновление; transition — разрешённый/отклонённый переход; list — фильтр/порядок/границы; delete — убрано/нет/тип возврата; `__global_model__` — своя/чужая компания; composite key — совпадение всех частей/одной нет.

## Первопричина потери типа

Когда: режим `types`, S1 — basedpyright, `cast`, `object`, `Any`, `# type: ignore`.

1. Слепое пятно: `uv run basedpyright --level warning --warnings <paths>`, `ratchet_list.py cast_calls|object_annotations|type_ignore`.
2. Трассировка до правки: где данные появляются (БД, HTTP, SDK, JSON parser, registry, event bus, state, DI), кто владеет контрактом, кто потребляет. Источник не найден — работа не начата.
3. Строгий контракт на самой ранней границе: ответ внешнего API — Pydantic-модель на границе; payload события — одна модель для WS и REST; строка БД — `PlatformModel`; произвольный JSON — только `core/types.py` и только без известной схемы. Новый общий alias — `core/types.py`; доменный контракт — у владельца домена.
4. Протянуть тип по цепочке: payload/response, сервисы, модели, `<Process>Di`, задачи, события, тесты, UI-контракт JSON. Удалить ставшие ненужными `cast`, mapper, fallback, twin-модель.
5. Контрольные вопросы: `Any`/`Unknown` исчез из источника, а не спрятан ниже; тип переиспользуется всеми потребителями; нет второй модели сущности; нет `get(..., default)`/`or default`, маскирующих контракт. Любой ответ «нет» — срез не закончен.

## Twin-модели и мапперы

Когда: X1, X2.

1. Сравнить поля twin-модели и канонической модели сущности (`main.mdc` § Именование, «Модель» правила-владельца). Форма совпадает на 90% и больше — это одна модель.
2. Потребители (API `response_model`, события, UI-фабрики, тесты) переходят на каноническую модель; обогащение (вычисляемые поля) — поле канонической модели или отдельная модель реально другой формы.
3. Mapper между почти одинаковыми моделями удаляется вместе с одной из моделей. Конвертация на внешней границе (`main.mdc` § Внешняя граница) остаётся у владельца внешнего контракта.
4. Frontend: `mapItem` фабрики и `restMirror` обновляются под новый JSON в том же срезе.

## `HTTPException` → `raise_*`

Когда: T2.

1. Граница — один файл `apps/<svc>/api/*.py` или семейство эндпоинтов.
2. Эндпоинт команды: логика уходит в `op_*`/сервис, хендлер собирает payload и зовёт `op_*`; ошибки — `raise_*` (`core/websocket/operation.py`) или `Platform*Error` (`core/errors/boundary.py`).
3. Протокольный хендлер из `PROTOCOL_HANDLERS`: те же `raise_*`/`Platform*Error`; внешняя wire-спека со своим конвертом — `extra_exception_handlers` в `create_service_app`.
4. `error_code` — ключ `platform:errors.*` в ru и en; кириллица в аргументах `raise` запрещена (`scripts/gates/backend/backend_error_i18n.py`).
5. `ratchet_list.py http_exception_in_services` → число ниже; `check_ratchet_counts.py --update`.

## Клиент → `core/clients`

Когда: C2 — клиент в `apps/*/clients/`, прямой `httpx2`.

1. Существующий клиент того же сервиса в `core/clients/` — использовать его; нет — перенести класс в `core/clients/<service>_client.py` поверх `ServiceClient`.
2. Модель владельца доступна процессу (общая БД) — клиент не нужен: чтение через `await Model.method(...)` (`architecture.mdc` § Межсервисный доступ).
3. Все импорты — на новый путь; заменённый модуль убирается. Tools вызывают клиент тонким `@tool` (`tools.mdc`).
4. Прямой `httpx2.AsyncClient` к внешнему API — через `core/clients/` и `get_httpx_client` (`integrations.mdc`).

## Копипаста → `core`

Когда: C3, C4.

1. Сравнить копии построчно; расхождения — параметры (имя сервиса, язык, путь) или ошибки одной из копий.
2. Вынести общий модуль в `core/<domain>/`; различия — параметры конструктора или settings, не флаги поведения.
3. Сервисы импортируют модуль из `core/`; копии удаляются в том же срезе. Одинаковые boundary-хелперы — в `core/request_scope.py`.

## Глобальный геттер → DI

Когда: D1, D2 — `get_*_service()`, module-global singleton.

1. Найти всех вызывающих геттера; каждый — boundary (`di.<field>`) или внутренний класс (constructor dependency).
2. Компонент становится полем `<Process>Di` нужных процессов; ресурс с teardown или конфиг → примитивы — `@recipe` в `di.py`.
3. Удалить геттер и module-global; `scripts/gates/backend/dependency_injection.py` зелёный; `check_di(<Process>Di)` в тесте.
4. `BillingService` — только через DI / конструктор / параметр фабрики (`billing.mdc`).

## Дрейф правил

Когда: режим `rules`, R1.

1. `uv run python -m scripts.gates.repo.rules_drift`.
2. Мёртвый путь: найти фактическое место (`rg -n "class <Name>|def <name>" apps core`), исправить путь; символа нет — удалить упоминание вместе с нормой, если норма описывала несуществующее.
3. Норма противоречит коду: нарушен код — это срез `slice`, правило не меняется; правило описывает несуществующее — исправить as-is.
4. Стоп-слово: переписать норму императивом без истории.
5. Ссылки из кода на несуществующее правило — на правило-владельца (`main.mdc` § Навигация).
6. Проверка: `rules_drift.py` без нарушений по затронутым файлам; бюджет строк соблюдён.

## Добавить детектор

Когда: режим `gate`, норма с `[без гейта]`, или класс нарушения без гейта в срезе `slice`.

1. Выбрать существующий скрипт того же канона (`references/gates.md`): DI и boundary — `scripts/gates/backend/dependency_injection.py`; строгость — `scripts/gates/backend/wider_repo_strictness.py` или ratchet; транспорт — `scripts/gates/backend/rest_handlers_call_ops.py`; один `PlatformModel` на файл — `scripts/gates/backend/model_files.py`; UI — `scripts/gates/frontend/ui_canon.sh`. Нового нет — модуль `scripts/gates/<область>/<имя>.py` и строка в `scripts/gates/registry.py`.
2. Детектор — AST или точный regex, ограниченный границей нормы; вывод — `path:line: <норма>`; выход 1 при нарушении.
3. Запустить на текущем коде: детектор находит известные нарушения. Ничего не нашёл — он неверен.
4. Нарушений больше одного среза — ratchet-метрика: `RatchetMetric` в `scripts/gates/backend/ratchet_counts.py` и текущее число в `scripts/gates/backend/ratchet_baseline.json` (`--update`).
5. Новый скрипт — строка в `mk/lint.mk` (`_lint-py`) или зависимость `check-events-canon` в `Makefile`.
6. Правило-владелец: снять `[без гейта]`, добавить гейт в «Гейты»; allowlist — только пункты `Исключение:`.
7. Проверка: `gates_report.py` показывает новый шаг; `make lint` проходит, если остаток оформлен ratchet.
